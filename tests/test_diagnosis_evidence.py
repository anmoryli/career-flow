from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.diagnosis_evidence import evidence_rows
from app.services.diagnosis_references import ReferencedFinding, build_references, editable_targets


def test_retrieved_passage_is_exact_and_not_presented_as_model_evidence():
    document = {"summary": "负责Python数据处理与接口开发"}
    operation = SimpleNamespace(
        input_snapshot={"document": document, "jd": "需要Python数据处理"},
        result={
            "findings": [
                {
                    "requirement": "需要Python数据处理",
                    "category": "missing",
                    "evidence": "",
                    "source": "none",
                    "explanation": "待核对",
                }
            ]
        },
    )
    row = evidence_rows(operation)[0]
    assert row["passage"] == document["summary"]
    assert row["related"] is True
    assert row["target_path"] == "summary"
    assert row["category"] == "missing"


def test_reference_index_ignores_layout_and_includes_all_content_paragraphs():
    document = {
        "summary": "真实经历",
        "photo": "data:image/png;base64,AAA",
        "accent": "green",
        "section_order": ["summary"],
        "education": [{"school": "学校", "detail": "研究Python"}],
        "custom_sections": [{"title": "补充", "content": "项目补充"}],
    }
    refs = build_references({"document": document, "jd": "Python"})
    assert all(
        item["text"] not in {"green", "summary", document["photo"]}
        for item in refs["evidence"].values()
    )
    paths = {item["path"] for item in editable_targets(document).values()}
    assert {"summary", "education.0.detail", "custom_sections.0.content"} <= paths


def test_model_must_explicitly_supply_evidence_reference():
    with pytest.raises(ValidationError):
        ReferencedFinding(requirement_id="J0", category="missing", explanation="未核对")
