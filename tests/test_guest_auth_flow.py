import re
from io import BytesIO


def test_guest_can_open_resume_editor_and_keep_save_behind_login_modal(app):
    response = app.test_client().get("/workspace?view=resume-new")

    assert response.status_code == 200
    assert b"data-resume-editor" in response.data
    assert b"data-save-resume" in response.data
    assert b"id=\"auth-dialog\"" in response.data


def test_guest_job_page_offers_pdf_before_analysis_login(app):
    response = app.test_client().get("/workspace?view=jobs")

    assert response.status_code == 200
    assert b"guest-resume-file" in response.data
    assert b"data-save-job" in response.data
    assert b"id=\"auth-dialog\"" in response.data


def test_login_route_renders_standalone_auth_page_for_guests(app):
    response = app.test_client().get("/login?next=/workspace?view=jobs")

    # 整体前端重构后的既定行为：/login 渲染独立认证页（next 由前端脚本从 URL 读取），
    # 共享登录弹窗用于工作空间游客页，见 dc2a2e0 与 browser/craft、frontend_experience 用例。
    assert response.status_code == 200
    assert b'data-ui-form="auth"' in response.data


def test_anonymous_api_requests_return_json_login_signal(app):
    client = app.test_client()
    page = client.get("/")
    token = re.search(rb'name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    response = client.post("/api/resumes", json={}, headers={"X-CSRFToken": token})

    assert response.status_code == 401
    assert response.json["login_required"] is True
def test_guest_pdf_is_parsed_in_memory_before_authentication(app, monkeypatch):
    from app.services import infrastructure, pdf_import

    monkeypatch.setattr(infrastructure, "rate_limit", lambda *args: None)
    monkeypatch.setattr(pdf_import, "parse_pdf", lambda content: ("resume text", {"name": "Lin"}))
    client = app.test_client()
    page = client.get("/")
    token = re.search(rb'name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    response = client.post(
        "/api/guest/resume/parse",
        data={"file": (BytesIO(b"%PDF-test"), "resume.pdf")},
        headers={"X-CSRFToken": token},
    )

    assert response.status_code == 200
    assert response.json["text"] == "resume text"
    assert response.json["document"]["name"] == "Lin"
