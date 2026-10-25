import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Conversation,
    ConversationMemory,
    ConversationMessage,
    EmailVerificationCode,
    User,
    UserSession,
    utcnow,
)
from app.schemas import MemoryInput, MessageInput, RegisterInput
from app.services import auth
from app.services.conversations import append_message, build_context, save_memory
from app.services.errors import BusinessError

pytestmark = pytest.mark.integration


def csrf(client, path="/login"):
    response = client.get(path)
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)


def login_client(app, user_id):
    client = app.test_client()
    with app.app_context():
        token = auth.issue_session(db.session.get(User, user_id))
    client.set_cookie("cf_session", token)
    return client, token


def new_conversation(app, user_id):
    with app.app_context():
        item = Conversation(user_id=user_id, title="中文 / English 🟢")
        db.session.add(item)
        db.session.commit()
        return item.id


def test_mysql_version_schema_engine_charset(mysql_app):
    with mysql_app.app_context():
        assert db.session.scalar(text("SELECT VERSION()")).startswith("8.4.")
        assert db.session.scalar(text("SELECT version_num FROM alembic_version")) == "8d2c71ab4e90"
        rows = db.session.execute(
            text(
                "SELECT ENGINE,TABLE_COLLATION FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME != 'alembic_version'"
            )
        ).all()
        assert len(rows) == len(db.metadata.tables) == 24
        assert all(
            engine == "InnoDB" and collation == "utf8mb4_0900_ai_ci" for engine, collation in rows
        )
        assert len(inspect(db.engine).get_foreign_keys("conversation_memories")) == 1
    assert mysql_app.test_client().get("/health/ready").status_code == 200


def test_auth_persistent_cookie_login_logout(mysql_app, user_factory):
    uid, email = user_factory()
    client = mysql_app.test_client()
    response = client.post(
        "/login",
        data={
            "csrf_token": csrf(client),
            "email": email,
            "password": "valid-test-password",
        },
    )
    assert response.status_code == 303
    cookie = client.get_cookie("cf_session")
    assert cookie.http_only and cookie.same_site == "Lax" and cookie.expires
    with mysql_app.app_context():
        record = db.session.scalar(select(UserSession).where(UserSession.user_id == uid))
        assert record.token_hash != cookie.value
        assert record.token_hash == auth.digest_token(cookie.value)
    second = mysql_app.test_client()
    second.set_cookie("cf_session", cookie.value)
    assert second.get("/workspace").status_code == 200
    token = csrf(second, "/workspace")
    assert second.post("/logout", data={"csrf_token": token}).status_code == 303
    assert client.get("/workspace").status_code == 303


def test_session_expiry_and_revoke_all(mysql_app, user_factory):
    uid, _ = user_factory()
    first, token = login_client(mysql_app, uid)
    second, other = login_client(mysql_app, uid)
    with mysql_app.app_context():
        record = db.session.scalar(
            select(UserSession).where(
                UserSession.token_hash == auth.digest_token(token),
            )
        )
        record.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
    assert first.get("/workspace").status_code == 303
    csrf_token = csrf(second, "/workspace")
    assert second.post("/sessions/revoke", data={"csrf_token": csrf_token}).status_code == 303
    second.set_cookie("cf_session", other)
    assert second.get("/workspace").status_code == 303


def test_invalid_login_and_rate_limit(mysql_app, user_factory):
    _, email = user_factory()
    client = mysql_app.test_client()
    token = csrf(client)
    for index in range(11):
        response = client.post(
            "/login",
            data={
                "csrf_token": token,
                "email": email,
                "password": "wrong-password-value",
            },
        )
        assert response.status_code == (401 if index < 10 else 429)
        assert "password_hash" not in response.text


def test_login_failure_message_does_not_reveal_account_existence(mysql_app, user_factory):
    _, email = user_factory()
    with mysql_app.app_context():
        with pytest.raises(BusinessError) as existing_account:
            auth.authenticate(email, "wrong-password-value")
        with pytest.raises(BusinessError) as unknown_account:
            auth.authenticate(f"missing-{uuid4().hex}@example.com", "wrong-password-value")
    assert existing_account.value.status == unknown_account.value.status == 401
    assert str(existing_account.value) == str(unknown_account.value)
    assert "首次使用" in str(unknown_account.value)


def test_registration_code_attempts_expiry_and_single_use(mysql_app):
    email = f"code-{uuid4().hex}@example.com"
    payload = dict(
        email=email, code="123456", display_name="真实用户", password="long-valid-password"
    )
    with mysql_app.app_context():
        db.session.add(
            EmailVerificationCode(
                email=email,
                code_hash=auth.digest_code(email, "123456"),
                expires_at=utcnow() + timedelta(minutes=10),
            )
        )
        db.session.commit()
        for _ in range(5):
            with pytest.raises(BusinessError, match="不正确"):
                auth.register(RegisterInput(**(payload | {"code": "000000"})))
        with pytest.raises(BusinessError, match="失效"):
            auth.register(RegisterInput(**payload))
        record = db.session.scalar(
            select(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
            )
        )
        record.attempts = 0
        record.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        with pytest.raises(BusinessError, match="失效"):
            auth.register(RegisterInput(**payload))
        record.expires_at = utcnow() + timedelta(minutes=10)
        db.session.commit()
        user = auth.register(RegisterInput(**payload))
        uid = user.id
        assert auth.authenticate(email, "long-valid-password").id == uid
        with pytest.raises(BusinessError, match="失效"):
            auth.register(RegisterInput(**payload))
        db.session.execute(delete(User).where(User.id == uid))
        db.session.commit()


def test_isolation_xss_theme_and_delete(mysql_app, user_factory):
    uid, _ = user_factory()
    other_id, _ = user_factory()
    cid = new_conversation(mysql_app, uid)
    client, _ = login_client(mysql_app, uid)
    other, _ = login_client(mysql_app, other_id)
    path = f"/conversations/{cid}"
    assert other.get(path).status_code == 404
    token = csrf(other, "/workspace")
    for endpoint, data in [
        ("messages", {"content": "intrusion", "request_key": str(uuid4())}),
        ("memories", {"key": "x", "value": "y", "confirmed": "yes"}),
        ("delete", {"confirm": "delete"}),
    ]:
        assert (
            other.post(f"{path}/{endpoint}", data=data | {"csrf_token": token}).status_code == 404
        )
    token = csrf(client, path)
    data = {
        "content": "<script>alert('xss')</script> 中文 🟢",
        "request_key": str(uuid4()),
        "csrf_token": token,
    }
    assert client.post(path + "/messages", data=data).status_code == 303
    response = client.get(path)
    assert "&lt;script&gt;" in response.text
    assert "<script>alert" not in response.text
    assert (
        client.post(
            "/settings/theme", json={"theme": "dark"}, headers={"X-CSRFToken": token}
        ).status_code
        == 200
    )
    assert 'data-user-theme="dark"' in client.get(path).text
    with mysql_app.app_context():
        save_memory(uid, cid, MemoryInput(key="城市", value="杭州", confirmed="yes"))
        context = build_context(uid, cid)
        assert context["untrusted_user_data"]["facts"][0]["value"] == {"text": "杭州"}
    assert client.post(path + "/delete", data={"csrf_token": token}).status_code == 400
    assert (
        client.post(path + "/delete", data={"csrf_token": token, "confirm": "delete"}).status_code
        == 303
    )
    with mysql_app.app_context():
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == cid,
                )
            )
            == 0
        )
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(ConversationMemory)
                .where(
                    ConversationMemory.conversation_id == cid,
                )
            )
            == 0
        )
        with pytest.raises(BusinessError):
            build_context(uid, cid)


def test_concurrent_message_idempotency_and_rollback(mysql_app, user_factory):
    uid, _ = user_factory()
    cid = new_conversation(mysql_app, uid)
    data = MessageInput(content="唯一消息", request_key=uuid4())

    def send(_):
        with mysql_app.app_context():
            return append_message(uid, cid, data).id

    with ThreadPoolExecutor(max_workers=5) as pool:
        ids = list(pool.map(send, range(5)))
    assert len(set(ids)) == 1
    with mysql_app.app_context():
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == cid,
                )
            )
            == 1
        )
        with pytest.raises(BusinessError, match="不一致"):
            append_message(uid, cid, MessageInput(content="不同", request_key=data.request_key))
        db.session.rollback()
        db.session.add(
            ConversationMessage(
                conversation_id=cid,
                content="duplicate",
                role="user",
                request_key=str(data.request_key),
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        conversation = db.session.get(Conversation, cid)
        conversation.status = "completed"
        db.session.commit()
        with pytest.raises(BusinessError, match="只读"):
            append_message(uid, cid, MessageInput(content="blocked", request_key=uuid4()))


def test_context_restart_budget_and_unconfirmed_exclusion(mysql_app, user_factory, config):
    from app import create_app

    uid, _ = user_factory()
    cid = new_conversation(mysql_app, uid)
    with mysql_app.app_context():
        append_message(uid, cid, MessageInput(content="真实项目经历", request_key=uuid4()))
        save_memory(uid, cid, MemoryInput(key="偏好", value="远程", confirmed="yes"))
        db.session.add(
            ConversationMemory(
                conversation_id=cid, key="推测", value={"text": "假经历"}, provenance="ai_inferred"
            )
        )
        db.session.commit()
        assert build_context(uid, cid, 0) == {"untrusted_user_data": {"facts": [], "messages": []}}
    new_app = create_app(
        config
        | {
            "SQLALCHEMY_DATABASE_URI": mysql_app.config["SQLALCHEMY_DATABASE_URI"],
        }
    )
    with new_app.app_context():
        context = str(build_context(uid, cid))
        assert "真实项目经历" in context and "远程" in context
        assert "假经历" not in context
