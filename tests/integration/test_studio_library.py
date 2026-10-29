"""Actual library covers follow immutable, owner-scoped latest versions."""
from uuid import uuid4

import pytest

from app.career_schemas import ResumeSave
from app.services import career
from tests.integration.test_career import client_for

pytestmark = pytest.mark.integration


def test_library_covers_use_latest_owned_version(mysql_app, user_factory):
    owner, _ = user_factory()
    other, _ = user_factory()
    with mysql_app.app_context():
        resume = career.save_resume(owner, ResumeSave(
            request_key=uuid4(), title="我的简历", document={"name": "旧姓名"},
        ))
        career.save_resume(owner, ResumeSave(
            request_key=uuid4(), revision=resume["revision"], title="我的简历",
            document={"name": "新姓名", "summary": '<img src=x onerror="alert(1)">'},
        ), resume["id"])
        career.save_resume(other, ResumeSave(
            request_key=uuid4(), title="他人文档不可见", document={"name": "他人姓名不可见"},
        ))
    client, _ = client_for(mysql_app, owner)
    response = client.get("/workspace?view=resumes")
    assert response.status_code == 200
    assert "新姓名" in response.text
    assert "旧姓名" not in response.text
    assert "他人文档不可见" not in response.text
    assert "他人姓名不可见" not in response.text
    assert '<img src=x onerror="alert(1)">' not in response.text
    assert "data-document-thumbnail" in response.text
