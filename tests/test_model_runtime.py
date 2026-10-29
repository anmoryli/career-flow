import asyncio
import json

import httpx
import pytest
from openai import APITimeoutError
from pydantic_ai.exceptions import ModelAPIError

from app.services.model_fallback import model_unavailable
from app.services.model_runtime import diagnosis_job_seconds, provider_error


def wrapped_timeout():
    request = httpx.Request("POST", "https://model.example/v1/chat/completions")
    low = httpx.ReadTimeout("must-not-leak-secret", request=request)
    sdk = APITimeoutError(request=request)
    sdk.__cause__ = low
    outer = ModelAPIError("test-model", "must-not-leak-secret")
    outer.__cause__ = sdk
    return outer


def sse_output(output):
    content = json.dumps(output, ensure_ascii=False)
    events = []
    for offset in range(0, len(content), 45):
        events.append(
            {
                "id": "test-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": content[offset : offset + 45]},
                        "finish_reason": None,
                    }
                ],
            }
        )
    events.extend(
        [
            {
                "id": "test-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "test-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
            {
                "id": "test-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "test-model",
                "choices": [],
                "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
            },
        ]
    )
    return (
        "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    ).encode()


def test_wrapped_timeout_reaches_fallback_without_exposing_exception_text():
    error = wrapped_timeout()
    assert isinstance(provider_error(error), httpx.ReadTimeout)
    assert model_unavailable(error)


def test_wrapped_account_error_still_does_not_fail_over():
    from pydantic_ai.exceptions import ModelHTTPError

    error = ModelAPIError("test-model", "do-not-log")
    error.__cause__ = ModelHTTPError(401, "test-model", "secret")
    assert not model_unavailable(error)


def test_exception_cycle_does_not_hang():
    error = ModelAPIError("test-model", "cyclic")
    error.__cause__ = error
    assert provider_error(error) is error


def test_job_budget_covers_two_attempts_per_unique_model():
    snapshot = {"model": "primary", "model_candidates": ["primary", "backup", "last", "backup"]}
    assert diagnosis_job_seconds(snapshot) == 570
    assert diagnosis_job_seconds({"model": "one"}) == 210


def test_stream_has_a_wall_clock_deadline(app, monkeypatch):
    import openai

    import app.services.model_provider as provider

    client_class = openai.AsyncOpenAI

    async def stalled(request):
        await asyncio.sleep(1)
        raise AssertionError("deadline failed")

    def client(**kwargs):
        return client_class(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(stalled))
        )

    monkeypatch.setattr(openai, "AsyncOpenAI", client)
    monkeypatch.setattr(provider, "DIAGNOSIS_ATTEMPT_SECONDS", 0.05)
    app.config.update(
        AI_ENABLED=True,
        AI_API_KEY="test-key",
        AI_MODEL="test-model",
        AI_BASE_URL="https://model.example/v1",
    )
    with app.app_context(), pytest.raises(TimeoutError):
        provider.generate({"model": "test-model", "kind": "analysis", "document": {}, "jd": "test"})


def test_long_stream_exceeds_read_timeout_while_chunks_keep_arriving(app, monkeypatch):
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import openai

    import app.services.model_provider as provider
    from tests.integration.test_career import valid_output
    from tests.test_model_provider import snapshot

    payload = sse_output(valid_output(snapshot()))
    request_flags = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            request_flags.append(request["stream"])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            for event in payload.splitlines(keepends=True):
                self.wfile.write(event)
                self.wfile.flush()
                time.sleep(0.01)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client_class = openai.AsyncOpenAI

    def client(**kwargs):
        return client_class(
            **kwargs, http_client=httpx.AsyncClient(trust_env=False, timeout=kwargs["timeout"])
        )

    monkeypatch.setattr(openai, "AsyncOpenAI", client)
    monkeypatch.setattr(provider, "DIAGNOSIS_READ_SECONDS", 0.15)
    app.config.update(
        AI_ENABLED=True,
        AI_API_KEY="test-key",
        AI_MODEL="test-model",
        AI_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1",
    )
    try:
        started = time.monotonic()
        with app.app_context():
            result, tokens = provider.generate(snapshot())
        assert time.monotonic() - started > 0.15
        assert result["summary"] and tokens == 300
        assert request_flags == [True]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
