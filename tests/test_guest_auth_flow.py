import re
from io import BytesIO
from urllib.parse import parse_qs, urlparse


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


def test_login_route_opens_shared_modal_on_landing_page(app):
    response = app.test_client().get("/login?next=/workspace?view=jobs")

    assert response.status_code == 302
    target = urlparse(response.headers["Location"])
    assert target.path == "/"
    assert parse_qs(target.query)["auth"] == ["login"]
    assert parse_qs(target.query)["next"] == ["/workspace?view=jobs"]


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
