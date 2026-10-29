import copy
import json

import httpx
import pytest
from pydantic import ValidationError

from app.diagnosis_schemas import DiagnosisResult
from app.services.diagnosis import validate_output
from app.services.model_provider import generate
from tests.integration.test_career import valid_output


def snapshot():
    return {
        "document": {"summary": "产品经验"},
        "jd": "要求产品经验",
        "answers": [],
        "kind": "analysis",
        "rounds": 0,
        "model": "test-model",
    }


def test_pydantic_ai_adapter_contract_without_external_request(app, monkeypatch):
    import openai

    client_class = openai.AsyncOpenAI
    seen = []

    def respond(request):
        data = json.loads(request.content)
        seen.append(data)
        assert "tools" not in data
        from tests.test_model_runtime import sse_output

        assert data["stream"] is True
        assert data["stream_options"]["include_usage"] is True
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse_output(valid_output(snapshot())),
        )

    def client(**kwargs):
        return client_class(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        )

    monkeypatch.setattr(openai, "AsyncOpenAI", client)
    app.config.update(
        AI_ENABLED=True, AI_API_KEY="test-key", AI_BASE_URL="https://model.example/v1"
    )
    with app.app_context():
        result, tokens = generate(snapshot() | {"prompt_instructions": "补充审查重点"})
    assert tokens == 300 and result["summary"]
    assert len(seen) == 1
    assert "untrusted_user_data" in json.dumps(seen[0]["messages"])
    assert "连续短语" in json.dumps(seen[0]["messages"], ensure_ascii=False)
    assert "补充审查重点" in json.dumps(seen[0]["messages"], ensure_ascii=False)


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_dimensions",
        "invalid_score",
        "missing_dimensions",
        "extra_keys",
        "unsafe_path",
        "wrong_original",
        "wrong_jd",
        "fake_evidence",
        "multiple_questions",
    ],
)
def test_model_output_rejected(case):
    raw = copy.deepcopy(valid_output(snapshot()))
    if case == "duplicate_dimensions":
        raw["dimensions"][1] = raw["dimensions"][0]
    if case == "invalid_score":
        raw["dimensions"][0]["score"] = 101
    if case == "missing_dimensions":
        raw["dimensions"] = []
    if case == "extra_keys":
        raw["javascript"] = "alert(1)"
    if case == "unsafe_path":
        raw["suggestions"][0]["path"] = "__dict__"
    if case == "wrong_original":
        raw["suggestions"][0]["original"] = "不存在"
    if case == "wrong_jd":
        raw["findings"][0]["requirement"] = "不存在"
    if case == "fake_evidence":
        raw["findings"][0]["source"] = "none"
    if case == "multiple_questions":
        raw["question"] = "问题一？问题二？"
    with pytest.raises((ValidationError, ValueError)):
        validate_output(raw, snapshot())


def test_report_discards_question_and_uses_five_dimensions():
    data = snapshot() | {"kind": "report"}
    result = validate_output(valid_output(data), data)
    assert result["question"] == ""
    assert len(DiagnosisResult.model_validate(result).dimensions) == 5
    assert result["overall_score"] == 60


def test_duplicate_suggestion_and_inconsistent_stored_score_rejected():
    raw = valid_output(snapshot())
    raw["suggestions"].append(dict(raw["suggestions"][0]))
    with pytest.raises(ValueError, match="重复"):
        validate_output(raw, snapshot())
    result = validate_output(valid_output(snapshot()), snapshot())
    with pytest.raises(ValidationError, match="等权"):
        DiagnosisResult.model_validate(result | {"overall_score": 1})


def test_only_real_confirmed_answer_can_support_evidence():
    data = snapshot() | {
        "answers": [{"question": "问题中的推测", "answer": "真实回答", "skipped": False}]
    }
    raw = valid_output(data)
    raw["findings"][0].update(source="answer", evidence="真实回答")
    assert validate_output(raw, data)["findings"][0]["evidence"] == "真实回答"
    raw["findings"][0]["evidence"] = "问题中的推测"
    with pytest.raises(ValueError, match="证据"):
        validate_output(raw, data)
