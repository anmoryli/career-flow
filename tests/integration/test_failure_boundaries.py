from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.career_schemas import CopyResume, JobSave, ResumeSave
from app.diagnosis_schemas import AnswerInput, ApplySuggestion, QuoteInput
from app.extensions import db
from app.models import Diagnostic, Resume, utcnow
from app.services import career, diagnosis, pdf_import
from app.services.errors import BusinessError
from tests.integration.test_career import client_for, make_operation
from tests.integration.test_career_paths import minimal_pdf

pytestmark = pytest.mark.integration


def test_quote_replay_change_and_answer_replay_change(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        data = QuoteInput(request_key=uuid4(), kind="analysis")
        op = diagnosis.quote(uid, did, data)
        assert diagnosis.quote(uid, did, data).id == op.id
        with pytest.raises(BusinessError, match="不一致"):
            diagnosis.quote(uid, did, data.model_copy(update={"kind": "report"}))
        db.session.rollback()
        mysql_app.config["AI_MODEL"] = "changed-model"
        with pytest.raises(BusinessError, match="配置"):
            diagnosis.confirm(uid, op.id)
        db.session.rollback()
        mysql_app.config["AI_MODEL"] = ""
        diagnosis.confirm(uid, op.id)
        diagnosis.run_operation(op.id)
        diagnostic = diagnosis.owned(Diagnostic, uid, did)
        answer = AnswerInput(request_key=uuid4(), revision=diagnostic.revision, answer="真实回答")
        diagnosis.answer(uid, did, answer)
        with pytest.raises(BusinessError, match="不一致"):
            diagnosis.answer(uid, did, answer.model_copy(update={"answer": "不同回答"}))


def test_copy_source_conflict_new_revision_and_size(mysql_app, context):
    uid, rid, _, _ = context
    with mysql_app.app_context():
        key = uuid4()
        copied = career.copy_resume(uid, rid, CopyResume(request_key=key, title="副本"))
        assert copied["parent_id"] == rid
        with pytest.raises(BusinessError, match="来源"):
            career.save_resume(
                uid, ResumeSave(request_key=key, title="副本", document=copied["document"])
            )
        db.session.rollback()
        with pytest.raises(BusinessError, match="从零"):
            career.save_resume(uid, ResumeSave(request_key=uuid4(), revision=1, document={}))
        db.session.rollback()
        with pytest.raises(BusinessError, match="过大"):
            career.save_resume(
                uid,
                ResumeSave(
                    request_key=uuid4(), document={"experiences": [{"bullets": ["x" * 4200000]}]}
                ),
            )


def test_transaction_failure_rolls_back_resume(mysql_app, context, monkeypatch):
    uid = context[0]
    with mysql_app.app_context():
        before = db.session.scalar(
            select(func.count()).select_from(Resume).where(Resume.user_id == uid)
        )

        def fail(*a, **k):
            raise IntegrityError("injected", {}, Exception("private"))

        with monkeypatch.context() as patch:
            patch.setattr(db.session, "flush", fail)
            with pytest.raises(BusinessError, match="冲突"):
                career.save_resume(uid, ResumeSave(request_key=uuid4(), document={}))
        assert (
            db.session.scalar(select(func.count()).select_from(Resume).where(Resume.user_id == uid))
            == before
        )


def test_ai_payload_limit_and_edited_suggestions(mysql_app, context):
    uid, rid, _, did = context
    with mysql_app.app_context():
        oid = make_operation(uid, did).id
        diagnosis.confirm(uid, oid)
        diagnosis.run_operation(oid)
        data = ApplySuggestion(
            request_key=uuid4(),
            indices=[0],
            edits={0: "本人核实的新表述"},
            confirmed="yes",
            title="核实版",
        )
        assert (
            diagnosis.apply_suggestions(uid, oid, data)["document"]["summary"] == "本人核实的新表述"
        )
        with pytest.raises(BusinessError, match="已选择"):
            diagnosis.apply_suggestions(uid, oid, data.model_copy(update={"edits": {1: "未选"}}))
        db.session.rollback()
        career.save_resume(
            uid,
            ResumeSave(
                request_key=uuid4(),
                revision=1,
                document={"experiences": [{"bullets": ["x" * 100001]}]},
            ),
            rid,
        )
        job = career.save_job(
            uid, JobSave(request_key=uuid4(), resume_id=rid, resume_revision=2, description="要求")
        )
        diagnostic = diagnosis.get_diagnostic(uid, job["id"])
        with pytest.raises(BusinessError, match="文字过长"):
            make_operation(uid, diagnostic.id)


def test_pdf_duplicate_worker_limit_and_interruption(mysql_app, context, monkeypatch):
    with mysql_app.app_context():
        uid = context[0]
        item = pdf_import.create_import(uid, uuid4(), minimal_pdf())
        pdf_import.run_import(item.id)
        pdf_import.run_import(item.id)
        assert item.state == "ready"
        item = pdf_import.create_import(uid, uuid4(), minimal_pdf())
        item.created_at = utcnow() - timedelta(minutes=6)
        db.session.commit()
        assert diagnosis.recover_stale_tasks() == 1
        db.session.refresh(item)
        assert item.state == "failed" and item.content is None
        assert diagnosis.run_operation(999999999) is None
        assert pdf_import.run_import(999999999) is None
    too_many = minimal_pdf(page_count=21)
    with pytest.raises(pdf_import.PDFInputError, match="20"):
        pdf_import.parse_pdf(too_many)


def test_cli_health_and_repeated_completed_confirmation(mysql_app, context):
    runner = mysql_app.test_cli_runner()
    assert runner.invoke(args=["check-services"]).exit_code == 0
    uid, _, _, did = context
    with mysql_app.app_context():
        oid = make_operation(uid, did).id
        diagnosis.confirm(uid, oid)
        diagnosis.run_operation(oid)
    client, headers = client_for(mysql_app, uid)
    assert (
        client.post(f"/api/operations/{oid}/confirm", json={}, headers=headers).json["state"]
        == "succeeded"
    )
    assert (
        client.post(
            f"/api/diagnostics/{did}/answer",
            json={"request_key": str(uuid4()), "revision": 1, "answer": "已确认"},
            headers=headers,
        ).status_code
        == 200
    )
