import base64
import runpy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.career_schemas import JobSave, ResumeSave
from app.diagnosis_schemas import ApplySuggestion
from app.extensions import db
from app.models import Diagnostic, EmailVerificationCode, utcnow
from app.schemas import MemoryInput, RegisterInput
from app.services import auth, career, diagnosis, pdf_import
from app.services.conversations import save_memory
from app.services.errors import BusinessError
from tests.integration.test_career import make_operation
from tests.integration.test_career_paths import minimal_pdf

pytestmark = pytest.mark.integration


def test_registration_duplicate_account_rolls_back(mysql_app, user_factory):
    _, email = user_factory()
    with mysql_app.app_context():
        db.session.add(
            EmailVerificationCode(
                email=email,
                code_hash=auth.digest_code(email, "123456"),
                attempts=0,
                expires_at=utcnow() + timedelta(minutes=10),
            )
        )
        db.session.commit()
        with pytest.raises(BusinessError, match="注册未完成"):
            auth.register(
                RegisterInput(
                    email=email,
                    code="123456",
                    password="valid-test-password",
                    display_name="不能覆盖",
                )
            )
        assert auth.authenticate(email, "valid-test-password")
        db.session.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.email == email)
        )
        db.session.commit()


def test_registration_send_commit_failure_is_explicit(mysql_app, monkeypatch):
    email = f"commit-failure-{uuid4().hex}@example.com"
    with mysql_app.app_context():

        def fail():
            raise IntegrityError("injected", {}, Exception("do-not-expose"))

        with monkeypatch.context() as patch:
            patch.setattr(db.session, "commit", fail)
            with pytest.raises(BusinessError, match="处理中"):
                auth.send_registration_code(email)
        assert (
            db.session.scalar(
                select(EmailVerificationCode).where(EmailVerificationCode.email == email)
            )
            is None
        )


def test_resend_invalidates_previous_code(mysql_app, monkeypatch):
    email = f"resend-{uuid4().hex}@example.com"

    class SMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def send_message(self, *a):
            pass

    monkeypatch.setattr("smtplib.SMTP", SMTP)
    with mysql_app.app_context():
        auth.send_registration_code(email)
        record = db.session.scalar(
            select(EmailVerificationCode).where(EmailVerificationCode.email == email)
        )
        record.attempts = 4
        record.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        auth.send_registration_code(email)
        db.session.refresh(record)
        assert record.attempts == 0 and record.expires_at > utcnow()
        db.session.delete(record)
        db.session.commit()


def test_photo_decoding_format_disagreement_and_byte_limit(mysql_app, context, monkeypatch):
    raw = b"\x89PNG\r\n\x1a\n"

    class Decoder:
        width = 100
        height = 100
        format = "GIF"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    with mysql_app.app_context():
        with monkeypatch.context() as patch:
            patch.setattr("PIL.Image.open", lambda *a: Decoder())
            with pytest.raises(BusinessError, match="不能解码"):
                career.save_resume(
                    context[0],
                    ResumeSave(
                        request_key=uuid4(),
                        document={
                            "photo": "data:image/png;base64," + base64.b64encode(raw).decode()
                        },
                    ),
                )
        with pytest.raises(BusinessError, match="2.5 MB"):
            career.save_resume(
                context[0],
                ResumeSave(
                    request_key=uuid4(),
                    document={
                        "photo": "data:image/png;base64,"
                        + base64.b64encode(raw + b"0" * 2621441).decode()
                    },
                ),
            )


def test_late_pdf_result_cannot_replace_recovery(mysql_app, context, monkeypatch):
    with mysql_app.app_context():
        item = pdf_import.create_import(context[0], uuid4(), minimal_pdf())

        def recover_while_parsing(content):
            item.state = "failed"
            item.content = None
            item.error = "已回收"
            db.session.commit()
            return "late text", {}

        monkeypatch.setattr(pdf_import, "parse_pdf", recover_while_parsing)
        pdf_import.run_import(item.id)
        assert item.state == "failed" and item.text == "" and item.content is None


def test_worker_entrypoint_and_health_timeout(mysql_app, monkeypatch):
    seen = []
    monkeypatch.setattr("app.create_app", lambda: mysql_app)
    monkeypatch.setattr(
        "rq.worker.base.BaseWorker.work", lambda worker: seen.extend(worker.queue_names())
    )
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "app/worker.py"), run_name="__main__")
    assert seen == ["careerflow"]
    monkeypatch.setattr(
        "app.cli.readiness", lambda: {"mysql": False, "schema": False, "redis": False}
    )
    ticks = iter([0, 0, 2])
    sleeps = []
    monkeypatch.setattr(
        "app.cli.time", SimpleNamespace(monotonic=lambda: next(ticks), sleep=sleeps.append)
    )
    result = mysql_app.test_cli_runner().invoke(args=["check-services", "--wait", "1"])
    assert result.exit_code != 0 and sleeps == [2]


def test_report_readonly_blocks_memory_and_updates_require_confirmation(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        diagnostic = db.session.get(Diagnostic, did)
        cid = diagnostic.conversation_id
        save_memory(uid, cid, MemoryInput(key="方向", value="产品", confirmed="yes"))
        save_memory(uid, cid, MemoryInput(key="方向", value="增长产品", confirmed="yes"))
        operation = make_operation(uid, did, "report")
        diagnosis.confirm(uid, operation.id)
        diagnosis.run_operation(operation.id)
        with pytest.raises(BusinessError, match="只读"):
            save_memory(uid, cid, MemoryInput(key="方向", value="不应更新", confirmed="yes"))


def test_recovery_and_cancel_race_does_not_refund_twice(mysql_app, context, monkeypatch):
    uid, _, _, did = context
    with mysql_app.app_context():
        op = make_operation(uid, did)
        diagnosis.confirm(uid, op.id)
        op.created_at = utcnow() - timedelta(minutes=6)
        db.session.commit()
        original = diagnosis.owner_lock
        first = True

        def cancel_then_lock(user_id):
            nonlocal first
            if first:
                first = False
                diagnosis.cancel(uid, op.id)
            original(user_id)

        monkeypatch.setattr(diagnosis, "owner_lock", cancel_then_lock)
        assert diagnosis.recover_stale_tasks() == 0
        assert diagnosis.account(uid).available == 10000 and diagnosis.account(uid).frozen == 0


def test_recovery_does_not_cancel_a_task_that_just_started(mysql_app, context, monkeypatch):
    uid, _, _, did = context
    with mysql_app.app_context():
        op = make_operation(uid, did)
        diagnosis.confirm(uid, op.id)
        op.created_at = utcnow() - timedelta(minutes=6)
        db.session.commit()
        original = diagnosis.owner_lock
        first = True

        def start_then_lock(user_id):
            nonlocal first
            if first:
                first = False
                op.state = "running"
                op.started_at = utcnow()
                db.session.commit()
            original(user_id)

        monkeypatch.setattr(diagnosis, "owner_lock", start_then_lock)
        assert diagnosis.recover_stale_tasks() == 0
        assert diagnosis.account(uid).frozen == op.ceiling
        diagnosis.cancel(uid, op.id)


def test_hidden_content_not_sent_but_preserved_in_optimized_copy(mysql_app, context):
    uid, rid, _, _ = context
    with mysql_app.app_context():
        career.save_resume(
            uid,
            ResumeSave(
                request_key=uuid4(),
                revision=1,
                document={
                    "summary": "产品经验",
                    "experiences": [{"company": "不对外展示的公司"}],
                    "hidden_sections": ["experiences"],
                },
            ),
            rid,
        )
        job = career.save_job(
            uid,
            JobSave(
                request_key=uuid4(), resume_id=rid, resume_revision=2, description="要求产品经验"
            ),
        )
        diagnostic = diagnosis.get_diagnostic(uid, job["id"])
        op = make_operation(uid, diagnostic.id)
        assert op.input_snapshot["document"]["experiences"] == []
        diagnosis.confirm(uid, op.id)
        diagnosis.run_operation(op.id)
        result = diagnosis.apply_suggestions(
            uid,
            op.id,
            ApplySuggestion(
                request_key=uuid4(), indices=[0], confirmed="yes", title="保留隐藏内容的副本"
            ),
        )
        assert result["document"]["experiences"][0]["company"] == "不对外展示的公司"
        assert result["document"]["hidden_sections"] == ["experiences"]
