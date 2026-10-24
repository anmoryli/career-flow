import pytest

from app.services import auth
from app.services.errors import BusinessError
from tests.integration.test_career import client_for

pytestmark = pytest.mark.integration


def test_change_password_requires_current_and_revokes_every_session(mysql_app, user_factory):
    uid, email = user_factory()
    first, headers = client_for(mysql_app, uid)
    second, _ = client_for(mysql_app, uid)
    url = "/settings/password"
    payload = {
        "current_password": "wrong-password-value",
        "new_password": "a-new-test-password-123",
        "confirm_password": "a-new-test-password-123",
    }
    assert first.post(url, json=payload, headers=headers).status_code == 401
    assert first.get("/workspace").status_code == 200
    assert (
        first.post(
            url, json=payload | {"current_password": "valid-test-password"}, headers=headers
        ).status_code
        == 303
    )
    assert first.get("/workspace").status_code == 303
    assert second.get("/workspace").status_code == 303
    with mysql_app.app_context():
        assert auth.authenticate(email, "a-new-test-password-123").id == uid
        with pytest.raises(BusinessError):
            auth.authenticate(email, "valid-test-password")


def test_password_change_validation(mysql_app, user_factory):
    uid, _ = user_factory()
    client, headers = client_for(mysql_app, uid)
    base = {
        "current_password": "valid-test-password",
        "new_password": "a-new-test-password-123",
        "confirm_password": "different-password-456",
    }
    assert client.post("/settings/password", json=base, headers=headers).status_code == 422
    assert (
        client.post(
            "/settings/password",
            json=base
            | {
                "confirm_password": base["current_password"],
                "new_password": base["current_password"],
            },
            headers=headers,
        ).status_code
        == 422
    )
