import copy
import json

import httpx
import pytest

from app.services.diagnosis import validate_output
from app.services.diagnosis_references import (
    ReferencedDiagnosis,
    build_references,
    resolve_references,
)
from tests.integration.test_career import valid_output
from tests.test_model_provider import snapshot
from tests.test_model_runtime import sse_output


def test_references_preserve_exact_jd_and_original_text():
    data = snapshot()
    refs = build_references(data)
    raw = valid_output(data)
    output = ReferencedDiagnosis.model_validate(
        raw
        | {
            "findings": [
                {
                    "requirement_id": "J0",
                    "evidence_id": "E0",
                    "category": "hard",
                    "explanation": "该条原文有对应经历",
                }
            ],
            "suggestions": [{"target_id": "T0", "proposed": "具备产品经验", "reason": "改善表达"}],
        }
    )
    resolved = resolve_references(output, refs)
    assert resolved["findings"][0]["requirement"] == data["jd"]
    assert resolved["findings"][0]["evidence"] == data["document"]["summary"]
    assert resolved["suggestions"][0]["original"] == data["document"]["summary"]
    assert validate_output(resolved, data)["overall_score"] == 60


def test_unknown_reference_fails_instead_of_dropping_or_fabricating_evidence():
    data = snapshot()
    raw = valid_output(data)
    raw.update(
        findings=[
            {
                "requirement_id": "J0",
                "evidence_id": "E999",
                "category": "hard",
                "explanation": "不可信引用",
            }
        ],
        suggestions=[],
    )
    with pytest.raises(ValueError, match="未提供的证据编号"):
        resolve_references(ReferencedDiagnosis.model_validate(raw), build_references(data))


def test_skipped_answers_are_never_reference_evidence():
    data = snapshot() | {
        "answers": [
            {"answer": "未确认经历", "skipped": True},
            {"answer": "用户补充的真实回答", "skipped": False},
        ]
    }
    refs = build_references(data)
    evidence = list(refs["evidence"].values())
    assert not any(item["text"] == "未确认经历" for item in evidence)
    assert any(
        item["text"] == "用户补充的真实回答" and item["source"] == "answer" for item in evidence
    )


def test_cumulative_siliconflow_usage_is_not_added_per_chunk(app, monkeypatch):
    import openai

    from app.services.model_provider import generate

    original_client = openai.AsyncOpenAI
    source = sse_output(valid_output(snapshot()))
    events = []
    for line in source.decode().splitlines():
        if line.startswith("data: {"):
            event = json.loads(line[6:])
            event["usage"] = {
                "prompt_tokens": 3253,
                "completion_tokens": 1341,
                "total_tokens": 4594,
            }
            events.append("data: " + json.dumps(event) + "\n\n")
    payload = ("".join(events) + "data: [DONE]\n\n").encode()

    def respond(request):
        body = json.loads(request.content)
        assert body["stream_options"]["continuous_usage_stats"] is True
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=payload)

    def client(**kwargs):
        return original_client(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        )

    monkeypatch.setattr(openai, "AsyncOpenAI", client)
    app.config.update(
        AI_ENABLED=True,
        AI_API_KEY="test-key",
        AI_MODEL="test-model",
        AI_BASE_URL="https://api.siliconflow.cn/v1",
    )
    with app.app_context():
        result, tokens = generate(copy.deepcopy(snapshot()))
    assert tokens == 4594
    assert result["findings"][0]["evidence"] == "产品经验"
