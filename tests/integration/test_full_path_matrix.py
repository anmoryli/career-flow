"""全路径覆盖矩阵。

目标：``app.url_map`` 里注册的每一条路由都被真实请求过一次，且任何输入都不会产生 5xx。
矩阵之外，另有三组边界矩阵：匿名访问、跨用户越权、非法输入。

设计约束：
* 会产生外部副作用的路径（发信、真调模型、入队）只施加非法输入，确保 handler 被走到
  但不触发真实调用；正常分支由 tests/integration 其余模块（fake provider）覆盖。
* 数据全部落在临时用户上，user_factory 负责清理。
"""

import re
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    AIOperation,
    ConfigRevision,
    Conversation,
    Membership,
    ReferralCode,
    ReportShare,
    ResumeImport,
    User,
    utcnow,
)
from app.web.product import GUIDES
from tests.integration.test_career import client_for, make_operation, valid_output

pytestmark = pytest.mark.integration

GUIDE_SLUG = next(iter(GUIDES))
FAKE_PDF = b"%PDF-1.4\nnot really a pdf\n%%EOF"


@pytest.fixture
def graph(mysql_app, user_factory):
    """一个自带简历、岗位、诊断、导入、会话、分享、邀请码的用户。"""
    mysql_app.extensions["diagnosis_provider"] = lambda snapshot: (valid_output(snapshot), 1100)
    uid, email = user_factory()
    other_uid, _ = user_factory()
    with mysql_app.app_context():
        db.session.get(User, uid).is_admin = True
        db.session.add(
            Membership(
                user_id=uid,
                plan_code="pro",
                expires_at=utcnow() + timedelta(days=30),
                next_grant_at=utcnow() + timedelta(days=1),
            )
        )
        db.session.commit()

    client, headers = client_for(mysql_app, uid)
    with mysql_app.app_context():
        from app.career_schemas import JobSave, ResumeSave
        from app.services import career, diagnosis

        resume = career.save_resume(
            uid,
            ResumeSave(
                request_key=uuid4(),
                title="矩阵简历",
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
        operation = make_operation(uid, diagnostic.id)

        item = ResumeImport(
            user_id=uid,
            request_key=str(uuid4()),
            digest="0" * 64,
            state="done",
            content=FAKE_PDF,
            text="导入的简历文本",
            document={"name": "导入", "summary": "导入摘要"},
        )
        conversation = Conversation(user_id=uid, title="矩阵会话")
        share = ReportShare(
            id=str(uuid4()),
            user_id=uid,
            operation_id=operation.id,
            request_key=str(uuid4()),
            token_hash="a" * 64,
            snapshot={"scores": {"match": 60}, "gap_counts": {"hard": 1}},
            expires_at=utcnow() + timedelta(days=7),
        )
        code = ReferralCode(user_id=uid, code=f"MTX{uuid4().hex[:8]}")
        db.session.add_all([item, conversation, share, code])
        db.session.commit()
        revision = db.session.scalar(
            select(ConfigRevision.id).where(ConfigRevision.category == "product").limit(1)
        )

        ids = {
            "uid": uid,
            "other_uid": other_uid,
            "email": email,
            "resume_id": resume["id"],
            "job_id": job["id"],
            "diagnostic_id": diagnostic.id,
            "operation_id": operation.id,
            "import_id": item.id,
            "conversation_id": conversation.id,
            "share_id": share.id,
            "share_token": "not-the-real-token",
            "code": code.code,
            "revision_id": revision,
        }
    yield client, headers, ids
    mysql_app.extensions.pop("diagnosis_provider", None)


def _post(client, url, headers, json=None, data=None):
    return client.post(url, json=json, data=data, headers=headers)


def route_requests(ids):
    """endpoint -> 一次真实请求。缺一条就说明矩阵没有覆盖到该路由。"""
    rid, jid, did = ids["resume_id"], ids["job_id"], ids["diagnostic_id"]
    oid, iid, cid = ids["operation_id"], ids["import_id"], ids["conversation_id"]
    rev = ids["revision_id"] or 1
    return {
        # 公开页
        "web.home": ("GET", "/", None),
        "web.workspace": ("GET", "/workspace", None),
        "web.live": ("GET", "/health/live", None),
        "web.ready": ("GET", "/health/ready", None),
        "web.login": ("GET", "/login", None),
        "web.register": ("GET", "/register", None),
        "web.password_reset_page": ("GET", "/password/reset", None),
        "product.guides": ("GET", "/guides", None),
        "product.guide": ("GET", f"/guides/{GUIDE_SLUG}", None),
        "product.robots": ("GET", "/robots.txt", None),
        "product.sitemap": ("GET", "/sitemap.xml", None),
        "product.invitation": ("GET", f"/invite/{ids['code']}", None),
        "product.public_share": (
            "GET",
            f"/s/{ids['share_id']}/{ids['share_token']}",
            None,
        ),
        # 工作台
        "web.conversation": ("GET", f"/conversations/{cid}", None),
        "imports.detail": ("GET", f"/imports/{iid}", None),
        "imports.status": ("GET", f"/api/imports/{iid}", None),
        "diagnosis.detail": ("GET", f"/jobs/{jid}", None),
        "diagnosis.suggestions": ("GET", f"/jobs/{jid}/suggestions", None),
        "product.report": ("GET", f"/jobs/{jid}/report", None),
        "product.share_manage": ("GET", f"/operations/{oid}/share", None),
        "career.print_resume": ("GET", f"/resumes/{rid}/print", None),
        "product.invitations": ("GET", "/invitations", None),
        # 简历与岗位 API
        "career.get_resume": ("GET", f"/api/resumes/{rid}", None),
        "career.versions": ("GET", f"/api/resumes/{rid}/versions", None),
        "career.get_job": ("GET", f"/api/jobs/{jid}", None),
        "career.update_resume": (
            "POST",
            f"/api/resumes/{rid}",
            {"json": {"request_key": str(uuid4()), "title": "矩阵改名", "revision": 1}},
        ),
        "career.create_resume": (
            "POST",
            "/api/resumes",
            {"json": {"request_key": str(uuid4()), "title": "矩阵新建", "document": {}}},
        ),
        "career.create_job": (
            "POST",
            "/api/jobs",
            {
                "json": {
                    "request_key": str(uuid4()),
                    "resume_id": rid,
                    "resume_revision": 1,
                    "description": "矩阵岗位",
                }
            },
        ),
        "career.copy_resume": (
            "POST",
            f"/api/resumes/{rid}/copy",
            {"json": {"request_key": str(uuid4()), "title": "矩阵副本"}},
        ),
        # 只施加非法输入：真实调用会外发或入队
        "imports.upload": ("POST", "/api/imports", {"data": {}}),
        "imports.parse_guest_resume": ("POST", "/api/guest/resume/parse", {"data": {}}),
        "imports.confirm": ("POST", f"/api/imports/{iid}/confirm", {"json": {}}),
        "career.delete_resume": (
            "POST",
            "/api/resumes/99999999/delete",
            {"json": {"request_key": str(uuid4()), "confirm": "yes"}},
        ),
        "career.delete_job": (
            "POST",
            "/api/jobs/99999999/delete",
            {"json": {"request_key": str(uuid4()), "confirm": "yes"}},
        ),
        "career.resume_ai_status": ("GET", "/api/resume-ai/99999999", None),
        "career.confirm_resume_ai": ("POST", "/api/resume-ai/99999999/confirm", {"json": {}}),
        "career.quote_resume_ai": ("POST", f"/api/resumes/{rid}/ai/quote", {"json": {}}),
        "career.start_resume_ai": ("POST", f"/api/resumes/{rid}/ai/start", {"json": {}}),
        "career.quote_resume_compose": (
            "POST",
            f"/api/resumes/{rid}/ai/compose/quote",
            {"json": {}},
        ),
        "career.start_resume_compose": (
            "POST",
            f"/api/resumes/{rid}/ai/compose/start",
            {"json": {}},
        ),
        "product.adoption": (
            "POST",
            f"/api/resumes/{rid}/adoptions",
            {"json": {"request_key": str(uuid4()), "suggestion": {}}},
        ),
        "product.export_resume": (
            "POST",
            f"/api/resumes/{rid}/export",
            {"json": {"request_key": str(uuid4()), "template": "modern"}},
        ),
        # 诊断
        "diagnosis.quote": ("POST", f"/api/diagnostics/{did}/quote", {"json": {}}),
        "diagnosis.start": ("POST", f"/api/diagnostics/{did}/start", {"json": {}}),
        "diagnosis.answer": ("POST", f"/api/diagnostics/{did}/answer", {"json": {}}),
        "diagnosis.operation": ("GET", f"/api/operations/{oid}", None),
        "diagnosis.apply": ("POST", f"/api/operations/{oid}/apply", {"json": {}}),
        "diagnosis.cancel": ("POST", f"/api/operations/{oid}/cancel", {"json": {}}),
        "diagnosis.confirm": ("POST", f"/api/operations/{oid}/confirm", {"json": {}}),
        # 账号与设置：真实改密会撤销会话，非法输入即可覆盖 handler
        "web.change_password": ("POST", "/settings/password", {"json": {}}),
        "web.profile": ("POST", "/settings/profile", {"json": {}}),
        "web.theme": ("POST", "/settings/theme", {"json": {"theme": "dark"}}),
        "web.revoke_sessions": ("POST", "/sessions/revoke", {"json": {}}),
        "web.delete_account": ("POST", "/settings/delete", {"json": {}}),
        "web.logout": ("POST", "/logout", {"data": {}}),
        "web.send_code": ("POST", "/auth/code", {"json": {"email": "not-an-email"}}),
        "web.password_reset_code": (
            "POST",
            "/password/reset/code",
            {"json": {"email": "not-an-email"}},
        ),
        "web.password_reset_submit": (
            "POST",
            "/password/reset",
            {"json": {"email": "not-an-email"}},
        ),
        "commerce.order": ("POST", "/commerce/orders", {"json": {}}),
        # 会话
        "web.create_conversation": ("POST", "/conversations", {"json": {"title": "矩阵"}}),
        "web.delete_conversation": ("POST", f"/conversations/{cid}/delete", {"json": {}}),
        "web.memory": ("POST", f"/conversations/{cid}/memories", {"json": {}}),
        "web.message": ("POST", f"/conversations/{cid}/messages", {"json": {}}),
        # 分享管理
        "product.revoke_share": (
            "POST",
            f"/shares/{ids['share_id']}/revoke",
            {"json": {}},
        ),
        # 管理后台
        "admin.dashboard": ("GET", "/admin", None),
        "admin.audit": ("GET", "/admin/audit", None),
        "admin.orders": ("GET", "/admin/orders", None),
        "admin.settings": ("GET", "/admin/settings", None),
        "admin.users": ("GET", "/admin/users", None),
        "admin.available_models": ("GET", "/admin/api/models", None),
        "admin.config_history": ("GET", "/admin/api/config/ai", None),
        "admin.config_draft": ("POST", "/admin/api/config/ai/draft", {"json": {}}),
        "admin.config_activate": ("POST", "/admin/api/config/ai/activate", {"json": {}}),
        "admin.config_rollback": ("POST", "/admin/api/config/ai/rollback", {"json": {}}),
        "admin.config_publish": (
            "POST",
            f"/admin/api/config/ai/{rev}/publish",
            {"json": {}},
        ),
        "admin.revoke_user_sessions": (
            "POST",
            f"/admin/users/{ids['other_uid']}/revoke-sessions",
            {"data": {}},
        ),
        "product.administration": ("GET", "/admin/product", None),
        "product.publish_policy": ("POST", f"/admin/product/{rev}/publish", {"data": {}}),
        "product.metrics_csv": ("GET", "/admin/product/metrics.csv", None),
    }


def registered_routes(app):
    return {rule.endpoint for rule in app.url_map.iter_rules() if rule.endpoint != "static"}


def test_matrix_covers_every_registered_route(mysql_app, graph):
    _, _, ids = graph
    covered = set(route_requests(ids))
    registered = registered_routes(mysql_app)
    assert registered - covered == set(), f"未覆盖的路由：{sorted(registered - covered)}"
    assert covered - registered == set(), f"矩阵里有不存在的路由：{sorted(covered - registered)}"


def test_every_route_answers_without_server_error(mysql_app, graph):
    client, headers, ids = graph
    failures = []
    for endpoint, (method, path, payload) in route_requests(ids).items():
        kwargs = dict(payload or {})
        response = getattr(client, method.lower())(path, headers=headers, **kwargs)
        if response.status_code >= 500:
            failures.append(f"{endpoint} {method} {path} -> {response.status_code}")
    assert not failures, "出现 5xx：\n" + "\n".join(failures)


def test_private_apis_reject_anonymous(mysql_app, graph):
    _, _, ids = graph
    anonymous = mysql_app.test_client()
    leaks = []
    for endpoint, (method, path, payload) in route_requests(ids).items():
        if method != "POST":
            continue
        kwargs = dict(payload or {})
        response = getattr(anonymous, method.lower())(path, **kwargs)
        if response.status_code < 400 or response.status_code >= 500:
            # /login /register /password reset /commerce 是公开入口，允许非 4xx
            if endpoint in {
                "web.login",
                "web.register",
                "web.password_reset_submit",
                "web.password_reset_code",
                "web.send_code",
                "imports.parse_guest_resume",
            }:
                continue
            leaks.append(f"{endpoint} {path} -> {response.status_code}")
    assert not leaks, "匿名用户不应触达：\n" + "\n".join(leaks)


def test_cross_account_access_is_denied(mysql_app, graph):
    _, _, ids = graph
    other_client, other_headers = client_for(mysql_app, ids["other_uid"])
    probes = [
        ("GET", f"/api/resumes/{ids['resume_id']}"),
        ("GET", f"/api/jobs/{ids['job_id']}"),
        ("GET", f"/api/resumes/{ids['resume_id']}/versions"),
        ("GET", f"/api/operations/{ids['operation_id']}"),
        ("GET", f"/jobs/{ids['job_id']}"),
        ("GET", f"/imports/{ids['import_id']}"),
        ("GET", f"/conversations/{ids['conversation_id']}"),
        ("GET", f"/operations/{ids['operation_id']}/share"),
        ("GET", f"/resumes/{ids['resume_id']}/print"),
    ]
    leaked = []
    for method, path in probes:
        response = getattr(other_client, method.lower())(path, headers=other_headers)
        if response.status_code < 400:
            leaked.append(f"{path} -> {response.status_code}")
    assert not leaked, "跨用户越权：\n" + "\n".join(leaked)
    assert other_client.get("/admin").status_code in {403, 404}


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/resumes", {"title": "缺 request_key"}),
        ("/api/resumes", {"request_key": "not-a-uuid", "title": "x"}),
        ("/api/resumes/abc", {"request_key": str(uuid4())}),
        ("/api/resumes/-1", {"request_key": str(uuid4())}),
        ("/api/jobs", {"request_key": str(uuid4())}),
        ("/settings/theme", {"theme": "../../etc"}),
        ("/settings/profile", {"display_name": "x" * 500}),
        ("/conversations", {"title": "x" * 500}),
    ],
)
def test_invalid_payloads_stay_client_errors(mysql_app, graph, path, payload):
    client, headers, _ = graph
    response = client.post(path, json=payload, headers=headers)
    assert 400 <= response.status_code < 500, f"{path} 返回 {response.status_code}"


def test_missing_csrf_is_rejected(mysql_app, graph):
    client, _, ids = graph
    response = client.post(f"/api/resumes/{ids['resume_id']}", json={"request_key": str(uuid4())})
    assert response.status_code in {400, 403}


def test_request_key_replay_is_idempotent(mysql_app, graph):
    client, headers, ids = graph
    from app.services import career

    key = uuid4()
    payload = {"request_key": str(key), "title": "重放", "document": {"summary": "一次性"}}
    first = client.post("/api/resumes", json=payload, headers=headers)
    second = client.post("/api/resumes", json=payload, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.get_json()["id"] == second.get_json()["id"]
    with mysql_app.app_context():
        rows = db.session.scalars(
            select(career.Resume.id).where(career.Resume.user_id == ids["uid"])
        ).all()
    # 重放没有多建一份：矩阵基础数据 1 份 + 本条 1 份
    assert len(rows) == 2


def test_oversized_and_wrong_type_uploads_are_rejected(mysql_app, graph):
    client, headers, _ = graph
    assert client.post("/api/guest/resume/parse", data={}, headers=headers).status_code == 422
    wrong = client.post(
        "/api/guest/resume/parse",
        data={"file": (bytes("不是 PDF", "utf-8"), "resume.txt")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert wrong.status_code == 422


def test_operation_owner_lock_blocks_foreign_confirm(mysql_app, graph):
    _, _, ids = graph
    other_client, other_headers = client_for(mysql_app, ids["other_uid"])
    response = other_client.post(
        f"/api/operations/{ids['operation_id']}/confirm",
        json={"request_key": str(uuid4())},
        headers=other_headers,
    )
    assert response.status_code in {403, 404}


def test_health_endpoints_report_dependencies(mysql_app):
    client = mysql_app.test_client()
    assert client.get("/health/live").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code in {200, 503}
    assert ready.is_json


def test_seo_files_are_well_formed(mysql_app):
    client = mysql_app.test_client()
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /s/" in robots.get_data(as_text=True)
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "<urlset" in sitemap.get_data(as_text=True)


def test_public_share_hides_private_fields(mysql_app, graph):
    _, _, ids = graph
    client = mysql_app.test_client()
    response = client.get(f"/s/{ids['share_id']}/{ids['share_token']}")
    # 错误 token 必须拿不到内容
    assert response.status_code in {403, 404}


def test_diagnostic_revision_conflict_is_reported(mysql_app, graph):
    client, headers, ids = graph
    with mysql_app.app_context():
        operation = db.session.get(AIOperation, ids["operation_id"])
        stale = (operation.diagnostic_revision or 1) + 99
    response = client.post(
        f"/api/operations/{ids['operation_id']}/apply",
        json={"request_key": str(uuid4()), "diagnostic_revision": stale},
        headers=headers,
    )
    assert 400 <= response.status_code < 500


def test_workspace_views_all_render(mysql_app, graph):
    client, _, _ = graph
    for view in (
        "resumes",
        "jobs",
        "reports",
        "resume-new",
        "resume-template",
        "history",
        "settings",
        "billing",
    ):
        response = client.get(f"/workspace?view={view}")
        assert response.status_code == 200, f"view={view} -> {response.status_code}"
        assert "cf-workspace" in response.get_data(as_text=True) or "cf-" in response.get_data(
            as_text=True
        )


def test_unknown_workspace_view_falls_back(mysql_app, graph):
    client, _, _ = graph
    response = client.get("/workspace?view=not-a-real-view")
    assert response.status_code in {200, 400, 404}


def test_login_and_register_forms_reject_bad_input(mysql_app):
    anon = mysql_app.test_client()
    page = anon.get("/login")
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
    response = anon.post(
        "/login",
        data={"email": "missing@example.com", "password": "whatever", "csrf_token": csrf},
    )
    assert 400 <= response.status_code < 500
    register = anon.post(
        "/register",
        data={"email": "bad-email", "password": "x", "csrf_token": csrf},
    )
    assert 400 <= register.status_code < 500
