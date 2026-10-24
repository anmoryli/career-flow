from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.diagnosis_schemas import AnswerInput
from app.extensions import db
from app.models import Diagnostic, StructuredInteraction
from app.services import diagnosis
from tests.integration.test_career import client_for, make_operation

pytestmark = pytest.mark.integration


def test_question_form_survives_reload_and_records_answer(mysql_app, context, user_factory):
    uid, _, jid, did = context
    with mysql_app.app_context():
        operation = make_operation(uid, did)
        diagnosis.confirm(uid, operation.id)
        diagnosis.run_operation(operation.id)
        item = db.session.scalar(
            select(StructuredInteraction).where(StructuredInteraction.operation_id == operation.id)
        )
        assert item.definition["conversation_state"] == "waiting_for_user"
        assert item.definition["blocks"][0]["fields"][0]["type"] == "textarea"
        form_id = item.id
        revision = db.session.get(Diagnostic, did).revision
    client, _ = client_for(mysql_app, uid)
    assert "能补充一个真实项目吗" in client.get(f"/jobs/{jid}").text
    other_uid, _ = user_factory()
    other, _ = client_for(mysql_app, other_uid)
    assert other.get(f"/jobs/{jid}").status_code == 404
    with mysql_app.app_context():
        with pytest.raises(ValidationError):
            diagnosis.answer(
                uid,
                did,
                AnswerInput(request_key=uuid4(), revision=revision, answer=""),
            )
        db.session.rollback()
        key = uuid4()
        diagnosis.answer(
            uid,
            did,
            AnswerInput(request_key=key, revision=revision, answer="真实项目经历"),
        )
        assert (
            diagnosis.answer(
                uid,
                did,
                AnswerInput(request_key=key, revision=revision, answer="真实项目经历"),
            ).rounds
            == 1
        )
        form = db.session.get(StructuredInteraction, form_id)
        assert form.state == "submitted"
        assert form.submission == {"answer": "真实项目经历"}
        assert form.request_key == str(key)
    assert "已回答 1/10 轮" in client.get(f"/jobs/{jid}").text


def test_report_supersedes_pending_question(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        first = make_operation(uid, did)
        diagnosis.confirm(uid, first.id)
        diagnosis.run_operation(first.id)
        second = make_operation(uid, did, "report")
        diagnosis.confirm(uid, second.id)
        diagnosis.run_operation(second.id)
        question = db.session.scalar(
            select(StructuredInteraction).where(StructuredInteraction.operation_id == first.id)
        )
        assert question.state == "superseded"
