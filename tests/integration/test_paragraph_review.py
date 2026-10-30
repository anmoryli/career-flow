from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.diagnosis_schemas import ApplySuggestion
from app.extensions import db
from app.models import AIOperation
from app.services import career, diagnosis
from app.services.errors import BusinessError
from tests.integration import test_career
from tests.integration.test_career import client_for, make_operation

context = test_career.context
pytestmark = pytest.mark.integration


def test_all_paragraphs_are_editable_without_ai_suggestions(mysql_app, context):
    uid, rid, jid, did = context
    with mysql_app.app_context():
        operation = make_operation(uid, did)
        diagnosis.confirm(uid, operation.id)
        diagnosis.run_operation(operation.id)
        operation.result = operation.result | {"suggestions": []}
        db.session.commit()
        oid = operation.id
        data = ApplySuggestion(
            request_key=uuid4(),
            confirmed="yes",
            title="手动核实岗位版",
            paragraph_edits={"summary": "具备产品经验，负责需求整理。"},
        )
        copied = diagnosis.apply_suggestions(uid, oid, data)
        assert copied["document"]["summary"] == "具备产品经验，负责需求整理。"
        assert copied["id"] != rid
        assert diagnosis.apply_suggestions(uid, oid, data)["id"] == copied["id"]
        assert (
            career.version_of(career.owned(test_career.Resume, uid, rid)).document["summary"]
            == "产品经验"
        )
    client, _ = client_for(mysql_app, uid)
    page = client.get(f"/jobs/{jid}/suggestions?operation_id={oid}")
    assert page.status_code == 200
    assert 'data-review-path="summary"' in page.text
    assert "重写这一段" in page.text


def test_review_rejects_missing_paragraph_and_foreign_operation(mysql_app, context, user_factory):
    uid, _, _, did = context
    foreign, _ = user_factory()
    with mysql_app.app_context():
        operation = make_operation(uid, did)
        diagnosis.confirm(uid, operation.id)
        diagnosis.run_operation(operation.id)
        data = ApplySuggestion(
            request_key=uuid4(),
            confirmed="yes",
            title="检查",
            paragraph_edits={"experiences.99.bullets.0": "伪造位置"},
        )
        with pytest.raises(BusinessError, match="已有的可编辑段落"):
            diagnosis.apply_suggestions(uid, operation.id, data)
        with pytest.raises(BusinessError):
            diagnosis.apply_suggestions(foreign, operation.id, data)
        assert db.session.get(AIOperation, operation.id).state == "succeeded"
    with pytest.raises(ValidationError):
        ApplySuggestion(
            request_key=uuid4(),
            confirmed="yes",
            title="非法路径",
            paragraph_edits={"__dict__": "bad"},
        )


def test_verified_addition_saves_new_version_and_is_idempotent(mysql_app, context):
    uid, rid, _, did = context
    with mysql_app.app_context():
        operation = make_operation(uid, did)
        diagnosis.confirm(uid, operation.id)
        diagnosis.run_operation(operation.id)
        data = ApplySuggestion(
            request_key=uuid4(),
            confirmed="yes",
            title="真实补充岗位版",
            additions=["实际负责Python数据清洗与接口联调。"],
        )
        copied = diagnosis.apply_suggestions(uid, operation.id, data)
        assert copied["id"] != rid
        assert copied["document"]["custom_sections"][-1]["content"] == data.additions[0]
        assert (
            copied["document"]["custom_sections"][-1]["id"]
            in copied["document"]["section_order"][-1]
        )
        assert diagnosis.apply_suggestions(uid, operation.id, data)["id"] == copied["id"]
        assert not career.version_of(career.owned(test_career.Resume, uid, rid)).document[
            "custom_sections"
        ]


def test_supplement_ai_uses_user_facts_and_checks_duplicate_payload(mysql_app, context):
    from app.resume_ai_schemas import ResumeAIQuote
    from app.services import resume_ai

    uid, rid, _, _ = context
    with mysql_app.app_context():
        resume = career.owned(test_career.Resume, uid, rid)
        request = ResumeAIQuote(
            request_key=uuid4(),
            revision=resume.revision,
            mode="generate",
            path="summary",
            source_facts="真实使用Python整理数据",
            requirement="要求十年Java管理经验",
        )
        operation = resume_ai.quote(uid, rid, request)
        assert operation.input_snapshot["original"] == request.source_facts
        assert "Java" not in str(operation.input_snapshot["context"])
        assert resume_ai.quote(uid, rid, request).id == operation.id
        changed = request.model_copy(update={"source_facts": "不同的真实输入"})
        with pytest.raises(BusinessError, match="重复请求"):
            resume_ai.quote(uid, rid, changed)
