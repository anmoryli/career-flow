import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.career_schemas import JobSave, ResumeSave
from app.diagnosis_schemas import AnswerInput, ApplySuggestion, QuoteInput
from app.extensions import db
from app.models import (
    AIOperation,
    Conversation,
    CreditEntry,
    Diagnostic,
    Membership,
    Resume,
    ResumeVersion,
    User,
    utcnow,
)
from app.services import auth, career, diagnosis
from app.services.errors import BusinessError

pytestmark = pytest.mark.integration


def valid_output(snapshot):
    return {
        "summary": "基于已提供的真实信息",
        "dimensions": [
            {"name": name, "score": 60, "reason": "简历已有产品经验，细节待确认"}
            for name in ["技能匹配", "岗位职责", "工作与项目经历", "成果与影响力", "学历及其他条件"]
        ],
        "findings": [
            {
                "requirement": "产品经验",
                "category": "hard",
                "source": "resume",
                "evidence": "产品经验",
                "explanation": "原文有体现",
            }
        ],
        "suggestions": [
            {
                "path": "summary",
                "original": "产品经验",
                "proposed": "具备产品经验",
                "reason": "表达更完整",
            }
        ],
        "question": "能补充一个真实项目吗？",
    }


@pytest.fixture
def context(mysql_app, user_factory):
    uid, _ = user_factory()
    with mysql_app.app_context():
        resume = career.save_resume(
            uid,
            ResumeSave(
                request_key=uuid4(),
                title="基础简历",
                document={"name": "测试", "summary": "产品经验"},
            ),
        )
        job = career.save_job(
            uid,
            JobSave(
                request_key=uuid4(),
                resume_id=resume["id"],
                resume_revision=1,
                description="要求产品经验",
            ),
        )
        diagnostic = diagnosis.get_diagnostic(uid, job["id"])
        db.session.add(
            Membership(
                user_id=uid,
                plan_code="membership_quarterly",
                expires_at=utcnow() + timedelta(days=90),
                next_grant_at=utcnow() + timedelta(days=90),
            )
        )
        db.session.commit()
        values = uid, resume["id"], job["id"], diagnostic.id
    mysql_app.extensions["diagnosis_provider"] = lambda snapshot: (valid_output(snapshot), 1100)
    yield values
    mysql_app.extensions.pop("diagnosis_provider", None)


def client_for(app, uid):
    client = app.test_client()
    with app.app_context():
        token = auth.issue_session(db.session.get(User, uid))
    client.set_cookie("cf_session", token)
    response = client.get("/workspace")
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', response.text).group(1)
    return client, {"X-CSRFToken": csrf}


def make_operation(uid, diagnostic_id, kind="analysis"):
    return diagnosis.quote(uid, diagnostic_id, QuoteInput(request_key=uuid4(), kind=kind))


def test_resume_save_retry_versions_conflict_and_copy(mysql_app, context):
    uid, rid, _, _ = context
    with mysql_app.app_context():
        data = ResumeSave(
            request_key=uuid4(), revision=1, title="新版", document={"summary": "新内容"}
        )
        first = career.save_resume(uid, data, rid)
        assert first["revision"] == 2
        assert career.save_resume(uid, data, rid) == first
        with pytest.raises(BusinessError, match="不一致"):
            career.save_resume(uid, data.model_copy(update={"title": "不同"}), rid)
        db.session.rollback()
        with pytest.raises(BusinessError, match="其他窗口"):
            career.save_resume(uid, data.model_copy(update={"request_key": uuid4()}), rid)
        db.session.rollback()
        from app.career_schemas import CopyResume

        copied = career.copy_resume(uid, rid, CopyResume(request_key=uuid4(), title="岗位版"))
        assert copied["parent_id"] == rid
        assert copied["document"]["summary"] == "新内容"
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(ResumeVersion)
                .where(ResumeVersion.resume_id == rid)
            )
            == 2
        )


@pytest.mark.parametrize(
    "path,method,payload",
    [
        ("/api/resumes/{r}", "get", None),
        ("/api/resumes/{r}/versions", "get", None),
        ("/resumes/{r}/print", "get", None),
        ("/workspace?view=resume-new&resume_id={r}", "get", None),
        ("/api/resumes/{r}", "post", {"request_key": str(uuid4()), "document": {}}),
        ("/api/resumes/{r}/copy", "post", {"request_key": str(uuid4()), "title": "复制"}),
        ("/api/resumes/{r}/delete", "post", {"confirm": "delete"}),
        ("/api/jobs/{j}/delete", "post", {"confirm": "delete"}),
        ("/jobs/{j}", "get", None),
        ("/api/diagnostics/{d}/quote", "post", {"request_key": str(uuid4()), "kind": "report"}),
        (
            "/api/diagnostics/{d}/answer",
            "post",
            {"request_key": str(uuid4()), "revision": 0, "skipped": True},
        ),
    ],
)
def test_cross_user_resource_isolation(mysql_app, context, user_factory, path, method, payload):
    _, rid, jid, did = context
    other, _ = user_factory()
    client, headers = client_for(mysql_app, other)
    response = getattr(client, method)(
        path.format(r=rid, j=jid, d=did), json=payload, headers=headers
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "document",
    [
        {"name": "x" * 81},
        {"unexpected": "x"},
        {"projects": [{}] * 21},
        {"photo": "javascript:alert(1)"},
        {"photo": "data:image/png;base64,AAAA"},
        {"summary": "x" * 601},
        {"experiences": [{"company": "x" * 121}]},
    ],
)
def test_invalid_resume_inputs(mysql_app, context, document):
    client, headers = client_for(mysql_app, context[0])
    response = client.post(
        "/api/resumes", json={"request_key": str(uuid4()), "document": document}, headers=headers
    )
    assert response.status_code == 422


def test_resume_csrf_auth_and_xss(mysql_app, context):
    client, headers = client_for(mysql_app, context[0])
    assert mysql_app.test_client().get(f"/api/resumes/{context[1]}").status_code == 401
    assert client.post("/api/resumes", json={}).status_code == 400
    response = client.post(
        "/api/resumes",
        json={
            "request_key": str(uuid4()),
            "title": "<script>alert(1)</script>",
            "document": {"name": "<img src=x onerror=alert(1)>"},
        },
        headers=headers,
    )
    assert response.status_code == 201
    html = client.get(f"/resumes/{response.json['id']}/print").text
    assert "<img src=x" not in html and "&lt;img" in html
    assert "<script>alert(1)</script>" not in client.get("/workspace?view=resumes").text


def test_job_immutable_version_and_delete_guards(mysql_app, context):
    uid, rid, jid, did = context
    client, headers = client_for(mysql_app, uid)
    assert (
        client.post(
            f"/api/resumes/{rid}/delete", json={"confirm": "delete"}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/jobs/{jid}/delete", json={"confirm": "delete"}, headers=headers
        ).status_code
        == 409
    )
    with mysql_app.app_context():
        diagnostic = db.session.get(Diagnostic, did)
        cid = diagnostic.conversation_id
    assert (
        client.post(
            f"/conversations/{cid}/delete", data={"confirm": "delete"}, headers=headers
        ).status_code
        == 409
    )
    assert client.get(f"/jobs/{jid}").status_code == 200


def test_success_billing_report_readonly_and_apply(mysql_app, context):
    uid, rid, _, did = context
    with mysql_app.app_context():
        op = make_operation(uid, did, "report")
        oid = op.id
        diagnosis.confirm(uid, oid)
        diagnosis.confirm(uid, oid)
        assert op.ceiling == 0
        diagnosis.run_operation(oid)
        diagnosis.run_operation(oid)
        op = db.session.get(AIOperation, oid)
        assert op.state == "succeeded" and op.charged == 0
        assert op.result["question"] == ""
        diagnostic = db.session.get(Diagnostic, did)
        assert diagnostic.state == "completed"
        assert db.session.get(Conversation, diagnostic.conversation_id).status == "readonly"
        data = ApplySuggestion(request_key=uuid4(), indices=[0], confirmed="yes", title="????")
        copied = diagnosis.apply_suggestions(uid, oid, data)
        assert copied["parent_id"] == rid and copied["document"]["summary"]
        assert diagnosis.apply_suggestions(uid, oid, data)["id"] == copied["id"]
        assert career.version_of(career.owned(Resume, uid, rid)).document["summary"]
        assert not db.session.scalars(
            select(CreditEntry).where(CreditEntry.operation_id == oid)
        ).all()
        with pytest.raises(BusinessError):
            make_operation(uid, did)

def test_suggestion_review_has_its_own_private_page(mysql_app, context, user_factory):
    uid, _, jid, did = context
    with mysql_app.app_context():
        operation = make_operation(uid, did, "report")
        diagnosis.confirm(uid, operation.id)
        diagnosis.run_operation(operation.id)
        operation_id = operation.id

    client, _ = client_for(mysql_app, uid)
    report = client.get(f"/jobs/{jid}")
    assert report.status_code == 200
    assert "查看并核实建议" in report.text
    assert 'data-apply-suggestions=' not in report.text

    page = client.get(f"/jobs/{jid}/suggestions?operation_id={operation_id}")
    assert page.status_code == 200
    assert 'data-analysis-page="review"' in page.text
    assert "核对建议，保存岗位简历" in page.text
    assert "简历原文" in page.text and "替换正文" in page.text
    assert page.text.count('name="suggestion"') >= 1

    other_uid, _ = user_factory()
    other, _ = client_for(mysql_app, other_uid)
    assert other.get(f"/jobs/{jid}/suggestions?operation_id={operation_id}").status_code == 404


def test_analysis_does_not_create_credit_ledger_entries(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        op = make_operation(uid, did)
        diagnosis.confirm(uid, op.id)
        diagnosis.run_operation(op.id)
        assert op.state == "succeeded" and op.ceiling == op.charged == 0
        assert not db.session.scalars(
            select(CreditEntry).where(CreditEntry.operation_id == op.id)
        ).all()

@pytest.mark.parametrize("mode", ["timeout", "invalid_json", "evidence", "usage", "path"])
def test_failures_retry_once_and_full_refund(mysql_app, context, mode):
    uid, _, _, did = context
    calls = []

    def provider(snapshot):
        calls.append(1)
        if mode == "timeout":
            raise TimeoutError("must-not-leak-secret")
        raw = valid_output(snapshot)
        if mode == "invalid_json":
            raw = {"unexpected": True}
        if mode == "evidence":
            raw["findings"][0]["evidence"] = "编造的经历"
        if mode == "path":
            raw["suggestions"][0]["path"] = "__class__"
        return raw, 0 if mode == "usage" else 100

    mysql_app.extensions["diagnosis_provider"] = provider
    with mysql_app.app_context():
        oid = make_operation(uid, did).id
        diagnosis.confirm(uid, oid)
        diagnosis.run_operation(oid)
        diagnosis.run_operation(oid)
        op = db.session.get(AIOperation, oid)
        assert op.state == "failed" and op.attempts == 2 and op.charged == 0
        assert len(calls) == 2
        assert "secret" not in op.error
        assert op.ceiling == op.charged == 0
    client, _ = client_for(mysql_app, uid)
    page = client.get(f"/jobs/{context[2]}")
    assert page.status_code == 200
    assert "岗位分析失败" in page.text
    assert (
        "连接模型服务超时" in page.text
        if mode == "timeout"
        else "模型返回内容不符合诊断格式" in page.text
    )
    assert "重试岗位分析" in page.text


def test_second_attempt_success_and_cancel_during_execution(mysql_app, context):
    uid, _, _, did = context
    calls = []

    def provider(snapshot):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError()
        return valid_output(snapshot), 500

    mysql_app.extensions["diagnosis_provider"] = provider
    with mysql_app.app_context():
        oid = make_operation(uid, did).id
        diagnosis.confirm(uid, oid)
        diagnosis.run_operation(oid)
        assert db.session.get(AIOperation, oid).attempts == 2
        oid2 = make_operation(uid, did).id
        diagnosis.confirm(uid, oid2)

        def cancel_provider(snapshot):
            diagnosis.cancel(uid, oid2)
            return valid_output(snapshot), 500

        mysql_app.extensions["diagnosis_provider"] = cancel_provider
        diagnosis.run_operation(oid2)
        assert db.session.get(AIOperation, oid2).state == "cancelled"
        assert db.session.get(AIOperation, oid2).charged == 0


def test_quote_expiry_and_no_model(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        op = make_operation(uid, did)
        op.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        with pytest.raises(BusinessError):
            diagnosis.confirm(uid, op.id)
        db.session.rollback()
        mysql_app.extensions.pop("diagnosis_provider", None)
        with pytest.raises(BusinessError):
            make_operation(uid, did)

def test_answer_skip_counts_ten_and_replay(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        for index in range(10):
            oid = make_operation(uid, did).id
            diagnosis.confirm(uid, oid)
            diagnosis.run_operation(oid)
            diagnostic = db.session.get(Diagnostic, did)
            data = AnswerInput(
                request_key=uuid4(),
                revision=diagnostic.revision,
                skipped=index % 2 == 0,
                answer="真实项目" if index % 2 else "",
            )
            diagnosis.answer(uid, did, data)
            diagnosis.answer(uid, did, data)
        assert db.session.get(Diagnostic, did).rounds == 10
        with pytest.raises(BusinessError, match="十轮"):
            make_operation(uid, did)


def test_concurrent_confirmation_is_idempotent_without_credit_ledger(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        oid = make_operation(uid, did).id
    def confirm_once(_):
        with mysql_app.app_context():
            return diagnosis.confirm(uid, oid).state
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(confirm_once, range(4))) == ["queued"] * 4
    with mysql_app.app_context():
        entries = db.session.scalar(
            select(func.count())
            .select_from(CreditEntry)
            .where(CreditEntry.operation_id == oid)
        )
        assert entries == 0
        diagnosis.cancel(uid, oid)
        diagnosis.cancel(uid, oid)
        assert db.session.get(AIOperation, oid).charged == 0
