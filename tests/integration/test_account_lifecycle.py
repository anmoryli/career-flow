import re
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.extensions import db
from app.models import (
    AdminAudit,
    AIOperation,
    AuthIdentity,
    Conversation,
    ConversationMessage,
    CreditAccount,
    CreditEntry,
    Diagnostic,
    DiagnosticAnswer,
    EmailVerificationCode,
    JobTarget,
    PasswordResetCode,
    Resume,
    ResumeVersion,
    User,
    UserSession,
    utcnow,
)
from app.services import auth
from app.services.errors import BusinessError
from tests.integration.test_career import client_for
from tests.integration.test_mysql import login_client

pytestmark = pytest.mark.integration


def test_account_delete_requires_password_and_confirmation(mysql_app, user_factory):
    uid, email = user_factory()
    client, headers = client_for(mysql_app, uid)
    url = "/settings/delete"
    payload = {"password": "valid-test-password", "confirm": "delete"}
    assert client.post(url, json=payload | {"confirm": "yes"}, headers=headers).status_code == 422
    assert (
        client.post(url, json=payload | {"password": "wrong-password"}, headers=headers).status_code
        == 401
    )
    assert client.get("/workspace").status_code == 200
    assert client.post(url, json=payload, headers=headers).status_code == 303
    assert client.get("/workspace").status_code == 303
    with mysql_app.app_context():
        assert db.session.get(User, uid) is None
        assert db.session.scalar(select(User.id).where(User.email == email)) is None
        with pytest.raises(BusinessError):
            auth.authenticate(email, "valid-test-password")


def test_account_delete_removes_all_owned_rows(mysql_app, context):
    uid, rid, _, did = context
    client, headers = client_for(mysql_app, uid)
    probe = f"probe-{uuid4().hex}@example.com"
    with mysql_app.app_context():
        db.session.add(EmailVerificationCode(email=probe, code_hash="x", expires_at=utcnow()))
        db.session.add(
            PasswordResetCode(email=probe, code_hash="x", attempts=0, expires_at=utcnow())
        )
        conversation_id = db.session.scalar(
            select(Conversation.id).where(Conversation.user_id == uid)
        )
        db.session.add(
            ConversationMessage(
                conversation_id=conversation_id,
                role="user",
                content="hello",
                request_key=str(uuid4()),
            )
        )
        db.session.add(
            DiagnosticAnswer(
                diagnostic_id=did,
                round=1,
                request_key=str(uuid4()),
                question="q",
                answer="a",
                skipped=False,
            )
        )
        db.session.commit()
    missing = {"confirm": "delete"}
    assert client.post("/settings/delete", json=missing, headers=headers).status_code == 422
    response = client.post(
        "/settings/delete",
        json={"password": "valid-test-password", "confirm": "delete"},
        headers=headers,
    )
    assert response.status_code == 303
    with mysql_app.app_context():
        assert db.session.get(User, uid) is None
        assert db.session.get(Resume, rid) is None
        for model, column in (
            (AuthIdentity, AuthIdentity.user_id),
            (UserSession, UserSession.user_id),
            (Resume, Resume.user_id),
            (ResumeVersion, ResumeVersion.resume_id),
            (JobTarget, JobTarget.user_id),
            (Diagnostic, Diagnostic.user_id),
            (AIOperation, AIOperation.user_id),
            (CreditEntry, CreditEntry.user_id),
            (Conversation, Conversation.user_id),
        ):
            assert db.session.scalar(select(column).where(column == uid).limit(1)) is None, (
                model.__name__
            )
        assert db.session.get(CreditAccount, uid) is None
        # Codes outside the account stay untouched: they are keyed by email, not user.
        assert (
            db.session.scalar(
                select(EmailVerificationCode.id).where(EmailVerificationCode.email == probe)
            )
            is not None
        )
        db.session.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.email == probe)
        )
        db.session.execute(delete(PasswordResetCode).where(PasswordResetCode.email == probe))
        db.session.commit()


def test_account_delete_refuses_frozen_credits(mysql_app, user_factory):
    uid, _ = user_factory()
    client, headers = client_for(mysql_app, uid)
    url = "/settings/delete"
    payload = {"password": "valid-test-password", "confirm": "delete"}
    with mysql_app.app_context():
        db.session.add(CreditAccount(user_id=uid, available=0, frozen=5))
        db.session.commit()
    assert client.post(url, json=payload, headers=headers).status_code == 409
    with mysql_app.app_context():
        account = db.session.get(CreditAccount, uid)
        account.frozen = 0
        account.available = 5
        db.session.commit()
    assert client.post(url, json=payload, headers=headers).status_code == 303
    with mysql_app.app_context():
        assert db.session.get(User, uid) is None


def test_account_delete_refuses_inflight_ai_work(mysql_app, context):
    from app.services import diagnosis
    from tests.integration.test_career import make_operation

    uid, _, _, did = context
    client, headers = client_for(mysql_app, uid)
    payload = {"password": "valid-test-password", "confirm": "delete"}
    with mysql_app.app_context():
        operation = make_operation(uid, did)
        assert operation.state == "quoted"
        operation_id = operation.id
        diagnosis.confirm(uid, operation_id)
    assert client.post("/settings/delete", json=payload, headers=headers).status_code == 409
    with mysql_app.app_context():
        diagnosis.cancel(uid, operation_id)
    assert client.post("/settings/delete", json=payload, headers=headers).status_code == 303
    with mysql_app.app_context():
        assert db.session.get(User, uid) is None


def test_admin_account_cannot_self_delete(mysql_app, user_factory):
    uid, _ = user_factory()
    with mysql_app.app_context():
        db.session.get(User, uid).is_admin = True
        db.session.commit()
    client, headers = client_for(mysql_app, uid)
    response = client.post(
        "/settings/delete",
        json={"password": "valid-test-password", "confirm": "delete"},
        headers=headers,
    )
    assert response.status_code == 403
    with mysql_app.app_context():
        assert db.session.get(User, uid) is not None
        db.session.get(User, uid).is_admin = False
        # Audit rows also block self-deletion: their FK is RESTRICT by design.
        db.session.add(
            AdminAudit(actor_id=uid, action="config_publish", target="model", request_id="t")
        )
        db.session.commit()
    response = client.post(
        "/settings/delete",
        json={"password": "valid-test-password", "confirm": "delete"},
        headers=headers,
    )
    assert response.status_code == 403
    with mysql_app.app_context():
        db.session.execute(delete(AdminAudit).where(AdminAudit.actor_id == uid))
        db.session.commit()


def test_admin_revokes_user_sessions_with_audit(mysql_app, user_factory):
    admin_id, _ = user_factory()
    with mysql_app.app_context():
        db.session.get(User, admin_id).is_admin = True
        db.session.commit()
    admin, _ = login_client(mysql_app, admin_id)
    target_id, _ = user_factory()
    first, _ = login_client(mysql_app, target_id)
    second, _ = login_client(mysql_app, target_id)
    assert first.get("/workspace").status_code == 200
    assert second.get("/workspace").status_code == 200

    token = re.search(r'name="csrf-token" content="([^"]+)"', admin.get("/admin/users").text).group(
        1
    )
    url = f"/admin/users/{target_id}/revoke-sessions"
    assert admin.post(url, headers={"X-CSRFToken": token}).status_code == 303
    assert first.get("/workspace").status_code == 303
    assert second.get("/workspace").status_code == 303
    with mysql_app.app_context():
        entry = db.session.scalar(
            select(AdminAudit).where(
                AdminAudit.actor_id == admin_id, AdminAudit.action == "revoke_sessions"
            )
        )
        assert entry is not None
        assert entry.target == f"user:{target_id}"
        assert (
            db.session.scalar(
                select(UserSession.id).where(UserSession.user_id == target_id).limit(1)
            )
            is None
        )
        db.session.execute(delete(AdminAudit).where(AdminAudit.actor_id == admin_id))
        db.session.commit()
    assert (
        admin.post(
            "/admin/users/999999/revoke-sessions", headers={"X-CSRFToken": token}
        ).status_code
        == 404
    )


def test_admin_revoke_requires_admin(mysql_app, user_factory):
    ordinary_id, _ = user_factory()
    ordinary, _ = login_client(mysql_app, ordinary_id)
    token = re.search(
        r'name="csrf-token" content="([^"]+)"', ordinary.get("/workspace").text
    ).group(1)
    url = f"/admin/users/{ordinary_id}/revoke-sessions"
    assert ordinary.post(url, headers={"X-CSRFToken": token}).status_code == 403
    anonymous = mysql_app.test_client()
    anonymous_token = re.search(
        r'name="csrf-token" content="([^"]+)"', anonymous.get("/login").text
    ).group(1)
    assert anonymous.post(url, headers={"X-CSRFToken": anonymous_token}).status_code == 303
