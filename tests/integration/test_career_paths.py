import base64
import io
from datetime import timedelta
from uuid import uuid4

import pytest
from PIL import Image

from app.career_schemas import JobSave, ResumeSave
from app.extensions import db
from app.models import AIOperation, Diagnostic, utcnow
from app.services import career, diagnosis, pdf_import
from app.services.errors import BusinessError
from tests.integration.test_career import client_for, make_operation

pytestmark = pytest.mark.integration


def test_api_resume_job_success_and_replay(mysql_app, context):
    uid = context[0]
    client, headers = client_for(mysql_app, uid)
    data = {"request_key": str(uuid4()), "title": "新简历", "document": {"summary": "内容"}}
    result = client.post("/api/resumes", json=data, headers=headers)
    rid = result.json["id"]
    assert result.status_code == 201
    assert client.get(f"/api/resumes/{rid}").json["document"]["summary"] == "内容"
    assert client.post("/api/resumes", json=data, headers=headers).json["id"] == rid
    assert client.get(f"/api/resumes/{rid}/versions").json["versions"][0]["revision"] == 1
    assert client.get(f"/resumes/{rid}/print?revision=12345").status_code == 404
    data.update(revision=1, request_key=str(uuid4()), title="新版")
    assert client.post(f"/api/resumes/{rid}", json=data, headers=headers).json["revision"] == 2
    job = {
        "request_key": str(uuid4()),
        "resume_id": rid,
        "resume_revision": 1,
        "description": "原始 JD",
    }
    result = client.post("/api/jobs", json=job, headers=headers)
    jid = result.json["id"]
    assert result.status_code == 201
    assert client.post("/api/jobs", json=job, headers=headers).json["id"] == jid
    job["description"] = "改过的 JD"
    assert client.post("/api/jobs", json=job, headers=headers).status_code == 409
    assert (
        client.post(
            f"/api/jobs/{jid}/delete", json={"confirm": "delete"}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/resumes/{rid}/delete", json={"confirm": "delete"}, headers=headers
        ).status_code
        == 200
    )
    assert client.get(f"/api/resumes/{rid}").status_code == 404


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///tmp/a", "//localhost/path"])
def test_job_source_invalid(mysql_app, context, url):
    with mysql_app.app_context(), pytest.raises(BusinessError):
        career.save_job(
            context[0],
            JobSave(
                request_key=uuid4(),
                resume_id=context[1],
                resume_revision=1,
                description="要求",
                url=url,
            ),
        )


@pytest.mark.parametrize("size,valid", [(100, True), (50, False), (4100, False)])
def test_photo_server_decoding(mysql_app, context, size, valid):
    output = io.BytesIO()
    Image.new("RGB", (size, size)).save(output, format="PNG")
    photo = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()
    with mysql_app.app_context():
        data = ResumeSave(request_key=uuid4(), document={"photo": photo})
        if valid:
            assert career.save_resume(context[0], data)["document"]["photo"] == photo
        else:
            with pytest.raises(BusinessError):
                career.save_resume(context[0], data)


def test_operation_endpoints_and_queue_failure(mysql_app, context, monkeypatch):
    uid, _, _, did = context
    client, headers = client_for(mysql_app, uid)
    quote = client.post(
        f"/api/diagnostics/{did}/quote",
        json={"kind": "analysis", "request_key": str(uuid4())},
        headers=headers,
    )
    assert quote.status_code == 200
    oid = quote.json["id"]
    assert client.get(f"/api/operations/{oid}").json["state"] == "quoted"

    def unavailable(*args, **kwargs):
        raise ConnectionError("private-connection-information")

    monkeypatch.setattr("app.web.diagnosis.Queue.enqueue", unavailable)
    response = client.post(f"/api/operations/{oid}/confirm", json={}, headers=headers)
    assert response.status_code == 503 and "private" not in response.text
    assert client.get(f"/api/operations/{oid}").json["state"] == "cancelled"
    credits = client.get("/api/credits").json
    assert credits["available"] == 10000 and credits["frozen"] == 0
    assert client.post(f"/api/operations/{oid}/cancel", json={}, headers=headers).status_code == 200


@pytest.mark.parametrize(
    "suffix,method,payload",
    [
        ("", "get", None),
        ("/confirm", "post", {}),
        ("/cancel", "post", {}),
        (
            "/apply",
            "post",
            {"request_key": str(uuid4()), "indices": [0], "confirmed": "yes", "title": "版本"},
        ),
    ],
)
def test_cross_user_operations(mysql_app, context, user_factory, suffix, method, payload):
    with mysql_app.app_context():
        oid = make_operation(context[0], context[3]).id
    other, _ = user_factory()
    client, headers = client_for(mysql_app, other)
    assert (
        getattr(client, method)(
            f"/api/operations/{oid}{suffix}", json=payload, headers=headers
        ).status_code
        == 404
    )


def test_task_crash_recovery_and_quoted_cancel(mysql_app, context):
    with mysql_app.app_context():
        uid, _, _, did = context
        op = make_operation(uid, did)
        diagnosis.cancel(uid, op.id)
        assert op.state == "cancelled" and diagnosis.account(uid).frozen == 0
        op = make_operation(uid, did)
        diagnosis.confirm(uid, op.id)
        op.created_at = utcnow() - timedelta(minutes=6)
        db.session.commit()
        assert diagnosis.recover_stale_tasks() == 1
        assert diagnosis.recover_stale_tasks() == 0
        assert diagnosis.account(uid).available == 10000
        assert db.session.get(AIOperation, op.id).state == "failed"


def test_state_change_invalidates_quote_and_answer_errors(mysql_app, context):
    from app.diagnosis_schemas import AnswerInput

    with mysql_app.app_context():
        uid, _, _, did = context
        op = make_operation(uid, did)
        diagnostic = db.session.get(Diagnostic, did)
        diagnostic.revision += 1
        db.session.commit()
        with pytest.raises(BusinessError):
            diagnosis.confirm(uid, op.id)
        db.session.rollback()
        with pytest.raises(BusinessError):
            diagnosis.answer(uid, did, AnswerInput(request_key=uuid4(), revision=1, skipped=True))


def minimal_pdf(text="email@example.com 13800138000", page_count=1):
    stream = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET".encode()
    kids = " ".join(f"{i + 3} 0 R" for i in range(page_count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode(),
    ]
    objects.extend(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources "
        f"<< /Font << /F1 {page_count + 3} 0 R >> >> /Contents {page_count + 4} 0 R >>".encode()
        for _ in range(page_count)
    )
    objects.extend(
        [
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        ]
    )
    result = b"%PDF-1.4\n"
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(result)
    result += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    result += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        result
        + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )


@pytest.mark.parametrize("mode", ["valid", "broken", "blank"])
def test_pdf_parse_and_binary_cleanup(mysql_app, context, mode):
    with mysql_app.app_context():
        content = (
            minimal_pdf()
            if mode == "valid"
            else minimal_pdf("")
            if mode == "blank"
            else b"%PDF-broken"
        )
        item = pdf_import.create_import(context[0], uuid4(), content)
        pdf_import.run_import(item.id)
        db.session.refresh(item)
        assert item.content is None
        assert item.state == ("ready" if mode == "valid" else "failed")
        if mode == "valid":
            assert item.document["email"] == "email@example.com"
            assert item.document["phone"] == "13800138000"
        else:
            assert item.error and item.document is None


def test_pdf_upload_confirm_authorization_and_errors(mysql_app, context, user_factory, monkeypatch):
    client, headers = client_for(mysql_app, context[0])
    monkeypatch.setattr("app.web.imports.Queue.enqueue", lambda *a, **k: None)
    key = str(uuid4())

    def upload(content, request_key=key):
        return client.post(
            "/api/imports",
            data={"request_key": request_key, "file": (io.BytesIO(content), "../../unsafe.pdf")},
            headers=headers,
        )

    response = upload(minimal_pdf())
    assert response.status_code == 201
    iid = response.json["id"]
    assert upload(minimal_pdf()).json["id"] == iid
    assert upload(minimal_pdf("different")).status_code == 409
    assert upload(b"invalid", str(uuid4())).status_code == 422
    assert upload(b"%PDF-" + b"0" * (4 * 1024 * 1024), str(uuid4())).status_code == 413
    assert upload(minimal_pdf(), "invalid-uuid").status_code == 422
    assert client.post("/api/imports", data={}, headers=headers).status_code == 422
    assert client.get(f"/api/imports/{iid}").json["state"] == "queued"
    assert client.get(f"/imports/{iid}").status_code == 200
    assert client.post(f"/api/imports/{iid}/confirm", json={}, headers=headers).status_code == 409
    with mysql_app.app_context():
        pdf_import.run_import(iid)
    assert upload(minimal_pdf()).json["state"] == "ready"
    assert client.post(f"/api/imports/{iid}/confirm", json={}, headers=headers).status_code == 422
    result = client.post(
        f"/api/imports/{iid}/confirm",
        json={"confirmed": "yes", "request_key": str(uuid4()), "document": {"name": "已核对"}},
        headers=headers,
    )
    assert result.status_code == 201
    other, _ = user_factory()
    other_client, other_headers = client_for(mysql_app, other)
    assert other_client.get(f"/api/imports/{iid}").status_code == 404
    assert (
        other_client.post(f"/api/imports/{iid}/confirm", json={}, headers=other_headers).status_code
        == 404
    )


def test_empty_missing_and_duplicate_apply(mysql_app, context):
    from app.diagnosis_schemas import ApplySuggestion

    with mysql_app.app_context():
        uid, _, _, did = context
        oid = make_operation(uid, did).id
        data = ApplySuggestion(request_key=uuid4(), indices=[0], confirmed="yes", title="新版本")
        with pytest.raises(BusinessError):
            diagnosis.apply_suggestions(uid, oid, data)
        diagnosis.confirm(uid, oid)
        diagnosis.run_operation(oid)
        with pytest.raises(BusinessError, match="编号"):
            diagnosis.apply_suggestions(uid, oid, data.model_copy(update={"indices": [-1]}))


def test_cli_credits_and_recovery(mysql_app, context):
    runner = mysql_app.test_cli_runner()
    assert runner.invoke(args=["grant-development-credits", str(context[0]), "10"]).exit_code == 0
    assert runner.invoke(args=["grant-development-credits", "999999999", "10"]).exit_code != 0
    assert runner.invoke(args=["recover-stale-tasks"]).exit_code == 0
    mysql_app.config["APP_ENV"] = "production"
    assert runner.invoke(args=["grant-development-credits", str(context[0]), "10"]).exit_code != 0
