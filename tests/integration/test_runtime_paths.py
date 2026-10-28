import io
import json
import re
import smtplib
import urllib.request
from uuid import uuid4

import pytest
from rq import Queue
from sqlalchemy import delete, select

from app.extensions import db
from app.models import AIOperation, EmailVerificationCode, ResumeImport, User
from app.services import auth, diagnosis, pdf_import
from app.services.errors import BusinessError
from app.worker import WindowsDevelopmentWorker
from tests.integration.test_career import client_for, make_operation
from tests.integration.test_career_paths import minimal_pdf

pytestmark = pytest.mark.integration


def test_real_local_mail_registration_and_login_flow(mysql_app):
    email = f"mail-path-{uuid4().hex}@example.com"
    uid = None
    client = mysql_app.test_client()
    token = re.search(r'name="csrf-token" content="([^"]+)"', client.get("/").text).group(1)
    headers = {"X-CSRFToken": token}
    response = client.post("/auth/code", json={"email": email}, headers=headers)
    assert response.status_code == 200
    assert client.post("/auth/code", json={"email": email}, headers=headers).status_code == 429
    with urllib.request.urlopen(
        "http://127.0.0.1:8026/api/v1/messages?limit=100", timeout=5
    ) as response:
        messages = json.load(response)["messages"]
    message = next(item for item in messages if any(to["Address"] == email for to in item["To"]))
    with urllib.request.urlopen(
        f"http://127.0.0.1:8026/api/v1/message/{message['ID']}", timeout=5
    ) as response:
        body = json.load(response)["Text"]
    code = re.search(r"\b[0-9]{6}\b", body).group()
    try:
        response = client.post(
            "/register",
            json={
                "email": email,
                "code": code,
                "display_name": "真实邮件测试",
                "password": "valid-test-password",
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert client.get("/").status_code == 200
        with mysql_app.app_context():
            user = db.session.scalar(select(User).where(User.email == email))
            uid = user.id
            auth.send_registration_code(email)  # Existing accounts cannot be discovered by send.
        token = re.search(
            r'name="csrf-token" content="([^"]+)"', client.get("/workspace").text
        ).group(1)
        assert (
            client.post(
                "/login",
                json={"email": email, "password": "valid-test-password"},
                headers={"X-CSRFToken": token},
            ).status_code
            == 200
        )
    finally:
        with mysql_app.app_context():
            if uid:
                db.session.execute(delete(User).where(User.id == uid))
            db.session.execute(
                delete(EmailVerificationCode).where(EmailVerificationCode.email == email)
            )
            db.session.commit()


def test_smtp_failure_invalidates_code(mysql_app, monkeypatch):
    email = f"failure-{uuid4().hex}@example.com"

    def broken(*args, **kwargs):
        raise OSError("private-smtp-secret")

    monkeypatch.setattr(smtplib, "SMTP", broken)
    with mysql_app.app_context():
        with pytest.raises(BusinessError, match="邮件发送失败"):
            auth.send_registration_code(email)
        assert (
            db.session.scalar(
                select(EmailVerificationCode).where(EmailVerificationCode.email == email)
            )
            is None
        )


def test_mail_tls_auth_and_html_redirect(mysql_app, monkeypatch):
    calls = []

    class SMTP:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def starttls(self, **kw):
            calls.append("tls")

        def login(self, *a):
            calls.append("login")

        def send_message(self, message):
            calls.append("send")

    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    mysql_app.config.update(MAIL_USE_TLS=True, MAIL_USERNAME="test", MAIL_PASSWORD="test")
    client = mysql_app.test_client()
    token = re.search(r'name="csrf-token" content="([^"]+)"', client.get("/").text).group(1)
    email = f"tls-{uuid4().hex}@example.com"
    assert client.post("/auth/code", data={"email": email, "csrf_token": token}).status_code == 303
    assert calls == ["tls", "login", "send"]
    with mysql_app.app_context():
        db.session.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.email == email)
        )
        db.session.commit()


def test_real_rq_pdf_and_failed_ai_release(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        imported = pdf_import.create_import(uid, uuid4(), minimal_pdf())
        iid = imported.id
        operation = make_operation(uid, did)
        oid = operation.id
        diagnosis.confirm(uid, oid)
        queue = Queue(f"careerflow-test-{uuid4().hex}", connection=mysql_app.extensions["redis"])
        pdf_job = queue.enqueue("app.jobs.pdf_import_job", iid, job_timeout=30)
        ai_job = queue.enqueue("app.jobs.diagnosis_job", oid, job_timeout=60)
        worker = WindowsDevelopmentWorker([queue], connection=mysql_app.extensions["redis"])
        worker.work(burst=True, logging_level="WARNING")
        assert pdf_job.get_status(refresh=True) == "finished"
        assert ai_job.get_status(refresh=True) == "finished"
        db.session.expire_all()
        assert db.session.get(ResumeImport, iid).state == "ready"
        assert db.session.get(AIOperation, oid).state == "failed"
        operation = db.session.get(AIOperation, oid)
        assert operation.ceiling == operation.charged == 0
        pdf_job.delete()
        ai_job.delete()


def test_all_write_endpoints_require_csrf_and_auth(mysql_app):
    anonymous = mysql_app.test_client()
    token = re.search(r'name="csrf-token" content="([^"]+)"', anonymous.get("/").text).group(1)
    rules = [
        rule
        for rule in mysql_app.url_map.iter_rules()
        if rule.rule.startswith("/api/") and "POST" in rule.methods
    ]
    assert {rule.endpoint for rule in rules} == {
        "career.create_resume",
        "career.update_resume",
        "career.copy_resume",
        "career.delete_resume",
        "career.create_job",
        "career.delete_job",
        "career.quote_resume_ai",
        "career.quote_resume_compose",
        "career.confirm_resume_ai",
        "career.start_resume_ai",
        "career.start_resume_compose",
        "diagnosis.quote",
        "diagnosis.confirm",
        "diagnosis.start",
        "diagnosis.cancel",
        "diagnosis.answer",
        "diagnosis.apply",
        "imports.upload",
        "imports.confirm",
        "imports.parse_guest_resume",
    }
    for rule in rules:
        path = re.sub(r"<int:[^>]+>", "999999999", rule.rule)
        assert anonymous.post(path, json={}).status_code == 400, path
        response = anonymous.post(path, json={}, headers={"X-CSRFToken": token})
        assert response.status_code in {302, 303, 401, 422}, path


def test_pdf_upload_queue_unavailable(mysql_app, context, monkeypatch):
    client, headers = client_for(mysql_app, context[0])

    def broken(*a, **kw):
        raise ConnectionError()

    monkeypatch.setattr("app.web.imports.Queue.enqueue", broken)
    response = client.post(
        "/api/imports",
        data={"request_key": str(uuid4()), "file": (io.BytesIO(minimal_pdf()), "test.pdf")},
        headers=headers,
    )
    assert response.status_code == 503
    assert (
        client.post("/api/imports", data={"request_key": str(uuid4())}, headers=headers).status_code
        == 422
    )
    with mysql_app.app_context():
        imported = db.session.scalar(select(ResumeImport).where(ResumeImport.user_id == context[0]))
        assert imported.state == "failed" and imported.content is None


def test_personal_record_routes_confirmed_memory_and_delete(mysql_app, context):
    client, headers = client_for(mysql_app, context[0])
    response = client.post("/conversations", json={"title": "真实职业思考"}, headers=headers)
    assert response.status_code == 303
    path = response.headers["Location"]
    assert (
        client.post(
            f"{path}/memories",
            json={"key": "求职方向", "value": "产品经理", "confirmed": "yes"},
            headers=headers,
        ).status_code
        == 303
    )
    html = client.get(path).text
    assert "产品经理" in html
    assert client.post(f"{path}/delete", data={"confirm": "no"}, headers=headers).status_code == 400
    assert (
        client.post(f"{path}/delete", data={"confirm": "delete"}, headers=headers).status_code
        == 303
    )


def test_worker_probe_and_startup_maintenance_failure(mysql_app, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.jobs import infrastructure_probe
    from app.worker import main

    with mysql_app.app_context():
        assert infrastructure_probe() == {"mysql": True, "schema": True, "redis": True}
    seen = []
    monkeypatch.setattr("app.worker.create_app", lambda: mysql_app)
    monkeypatch.setattr(
        "rq.worker.base.BaseWorker.work", lambda worker: seen.extend(worker.queue_names())
    )
    main()
    assert seen == ["careerflow"]
    with mysql_app.app_context():
        worker = WindowsDevelopmentWorker(
            ["test-maintenance"], connection=mysql_app.extensions["redis"]
        )
        monkeypatch.setattr("rq.worker.base.BaseWorker.run_maintenance_tasks", lambda self: None)

        def fail():
            raise OperationalError("test", {}, Exception("private"))

        monkeypatch.setattr(diagnosis, "recover_stale_tasks", fail)
        worker.run_maintenance_tasks()  # Recovery failure must roll back without stopping worker.
