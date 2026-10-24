from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.extensions import db
from app.models import PasswordResetCode
from app.services import auth
from app.services.errors import BusinessError
from tests.integration.test_career import client_for

pytestmark = pytest.mark.integration


def test_password_reset_email_code_and_session_revocation(mysql_app, user_factory, monkeypatch):
    uid, email = user_factory()
    client, headers = client_for(mysql_app, uid)
    monkeypatch.setattr(auth.secrets, "randbelow", lambda _: 123456)
    assert client.get("/password/reset").status_code == 200
    response = client.post("/password/reset/code", json={"email": email}, headers=headers)
    assert response.status_code == 200
    assert "如果该邮箱已有账号" in response.json["message"]
    with mysql_app.app_context():
        record = db.session.scalar(
            select(PasswordResetCode).where(PasswordResetCode.email == email)
        )
        assert record is not None
        assert record.code_hash != "123456"
    payload = {
        "email": email,
        "code": "000000",
        "new_password": "new-reset-password-123",
        "confirm_password": "new-reset-password-123",
    }
    assert client.post("/password/reset", json=payload, headers=headers).status_code == 400
    assert client.get("/workspace").status_code == 200
    assert (
        client.post(
            "/password/reset", json=payload | {"code": "123456"}, headers=headers
        ).status_code
        == 303
    )
    assert client.get("/workspace").status_code == 303
    assert (
        client.post(
            "/password/reset", json=payload | {"code": "123456"}, headers=headers
        ).status_code
        == 400
    )
    with mysql_app.app_context():
        assert auth.authenticate(email, "new-reset-password-123").id == uid
        with pytest.raises(BusinessError):
            auth.authenticate(email, "valid-test-password")


def test_reset_request_does_not_disclose_missing_account(mysql_app):
    client = mysql_app.test_client()
    csrf = (
        client.get("/password/reset")
        .text.split('name="csrf-token" content="', 1)[1]
        .split('"', 1)[0]
    )
    email = f"missing-{uuid4().hex}@example.com"
    result = client.post(
        "/password/reset/code", json={"email": email}, headers={"X-CSRFToken": csrf}
    )
    assert result.status_code == 200
    assert "如果该邮箱已有账号" in result.json["message"]
    with mysql_app.app_context():
        assert (
            db.session.scalar(select(PasswordResetCode).where(PasswordResetCode.email == email))
            is None
        )


def test_reset_code_attempt_limit(mysql_app, user_factory):
    _, email = user_factory()
    client = mysql_app.test_client()
    csrf = (
        client.get("/password/reset")
        .text.split('name="csrf-token" content="', 1)[1]
        .split('"', 1)[0]
    )
    with mysql_app.app_context():
        from datetime import timedelta

        from app.models import utcnow

        db.session.add(
            PasswordResetCode(
                email=email,
                code_hash=auth.digest_reset_code(email, "123456"),
                attempts=0,
                expires_at=utcnow() + timedelta(minutes=10),
            )
        )
        db.session.commit()
    payload = {
        "email": email,
        "code": "000000",
        "new_password": "new-reset-password-123",
        "confirm_password": "new-reset-password-123",
    }
    for _ in range(5):
        assert (
            client.post("/password/reset", json=payload, headers={"X-CSRFToken": csrf}).status_code
            == 400
        )
    assert (
        client.post(
            "/password/reset", json=payload | {"code": "123456"}, headers={"X-CSRFToken": csrf}
        ).status_code
        == 400
    )
    with mysql_app.app_context():
        db.session.execute(delete(PasswordResetCode).where(PasswordResetCode.email == email))
        db.session.commit()
