import re
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.extensions import db
from app.models import ActiveConfig, AdminAudit, ConfigRevision, EmailVerificationCode, User
from app.services import admin_config, auth, diagnosis
from tests.integration.test_career import make_operation
from tests.integration.test_mysql import login_client

pytestmark = pytest.mark.integration


def token(client, path="/admin"):
    response = client.get(path)
    return re.search(r'name="csrf-token" content="([^"]+)"', response.text).group(1)


@pytest.fixture
def admin_client(mysql_app, user_factory):
    uid, _ = user_factory()
    with mysql_app.app_context():
        db.session.get(User, uid).is_admin = True
        db.session.commit()
    mysql_app.config["ADMIN_CONFIG_KEY"] = "local-test-key-" + "x" * 48
    client, _ = login_client(mysql_app, uid)
    yield client, uid
    with mysql_app.app_context():
        ids = db.session.scalars(
            select(ConfigRevision.id).where(ConfigRevision.author_id == uid)
        ).all()
        if ids:
            db.session.execute(delete(ActiveConfig).where(ActiveConfig.revision_id.in_(ids)))
        db.session.execute(delete(AdminAudit).where(AdminAudit.actor_id == uid))
        db.session.execute(delete(ConfigRevision).where(ConfigRevision.author_id == uid))
        db.session.commit()


def post(client, path, payload, csrf_token):
    return client.post(path, json=payload, headers={"X-CSRFToken": csrf_token})


def model_settings(model_id="test-model", **changes):
    return {
        "provider": "test-provider",
        "model_id": model_id,
        "base_url": "https://models.example.com/v1",
        "tokens_per_credit": 1000,
        "enabled": True,
    } | changes


def commerce_settings():
    return {
        "membership_30": {"price_yuan": "19.90", "credits": 30},
        "membership_90": {"price_yuan": "49.90", "credits": 30},
        "membership_365": {"price_yuan": "169.90", "credits": 30},
        "credit_pack_1": {"price_yuan": "9.90", "credits": 100},
        "credit_pack_2": {"price_yuan": "24.90", "credits": 300},
        "credit_pack_3": {"price_yuan": "69.90", "credits": 1000},
        "enabled": True,
    }


def test_commerce_configuration_publishes_exact_prices(mysql_app, admin_client):
    client, _ = admin_client
    csrf_token = token(client)
    assert "会员与积分套餐" in client.get("/admin/settings").text
    settings = commerce_settings()
    bad = post(
        client,
        "/admin/api/config/commerce/draft",
        {
            "label": "无效套餐",
            "settings": settings | {"membership_30": {"price_yuan": -1, "credits": 30}},
        },
        csrf_token,
    )
    assert bad.status_code == 422
    draft = post(
        client,
        "/admin/api/config/commerce/draft",
        {"label": "套餐", "settings": settings},
        csrf_token,
    )
    assert draft.status_code == 201
    assert draft.json["settings"]["membership_30"]["price_yuan"] == "19.90"
    assert (
        post(
            client,
            f"/admin/api/config/commerce/{draft.json['id']}/publish",
            {"confirm": True},
            csrf_token,
        ).status_code
        == 200
    )
    with mysql_app.app_context():
        active, revision = admin_config.runtime_commerce()
        assert revision == draft.json["id"]
        assert active.membership_30.price_yuan == Decimal("19.90")


def test_admin_access_and_model_secret_lifecycle(mysql_app, user_factory, admin_client):
    client, uid = admin_client
    anonymous = mysql_app.test_client()
    ordinary_uid, _ = user_factory()
    ordinary, _ = login_client(mysql_app, ordinary_uid)
    assert anonymous.get("/admin").status_code == 303
    assert ordinary.get("/admin").status_code == 403
    assert ordinary.get("/admin/users").status_code == 403
    assert ordinary.get("/admin/api/config/model").status_code == 403
    assert ordinary.get("/admin/api/models").status_code == 403
    assert client.get("/admin").status_code == 200
    assert client.get("/admin/settings").status_code == 200
    assert client.get("/admin/users").status_code == 200
    csrf_token = token(client)
    url = "/admin/api/config/model"
    secret = "test-only-api-secret-123"
    first = post(
        client,
        url + "/draft",
        {"label": "Model A", "settings": model_settings(), "secret": secret},
        csrf_token,
    )
    assert first.status_code == 201
    one = first.json["id"]
    assert secret not in first.text
    with mysql_app.app_context():
        assert secret not in db.session.get(ConfigRevision, one).encrypted_secret
        assert secret not in str(
            db.session.scalars(select(AdminAudit).where(AdminAudit.actor_id == uid)).all()
        )
    assert post(client, f"{url}/{one}/publish", {"confirm": False}, csrf_token).status_code == 422
    assert post(client, f"{url}/{one}/publish", {"confirm": True}, csrf_token).status_code == 200
    with mysql_app.app_context():
        active = admin_config.runtime_model()
        assert active["model_id"] == "test-model"
        assert active["secret"] == secret
        assert active["revision_id"] == one
    assert secret not in client.get(url).text
    assert secret not in client.get("/admin/audit").text
    changed = post(
        client,
        url + "/draft",
        {"label": "Model B", "settings": model_settings("model-b"), "secret": ""},
        csrf_token,
    )
    assert changed.status_code == 201
    two = changed.json["id"]
    assert post(client, f"{url}/{two}/publish", {"confirm": True}, csrf_token).status_code == 200
    with mysql_app.app_context():
        assert admin_config.runtime_model(one)["model_id"] == "test-model"
        assert admin_config.runtime_model()["model_id"] == "model-b"
        assert admin_config.runtime_model(use_environment=True)["revision_id"] is None
    rejected = post(
        client,
        url + "/draft",
        {"label": "Other provider", "settings": model_settings(provider="other"), "secret": ""},
        csrf_token,
    )
    assert rejected.status_code == 422
    local_endpoint = post(
        client,
        url + "/draft",
        {
            "label": "Private endpoint",
            "settings": model_settings(base_url="https://127.0.0.1/v1"),
            "secret": "local-test-secret",
        },
        csrf_token,
    )
    assert local_endpoint.status_code == 422
    rolled = post(client, url + "/rollback", {"revision_id": one, "confirm": True}, csrf_token)
    assert rolled.status_code == 200
    assert rolled.json["version"] == 3
    with mysql_app.app_context():
        assert admin_config.runtime_model()["model_id"] == "test-model"
        assert admin_config.runtime_model()["secret"] == secret
        assert db.session.get(ConfigRevision, one).state == "published"
        assert db.session.get(ConfigRevision, two).state == "published"


def test_mail_profile_switch_and_real_local_delivery(mysql_app, admin_client):
    client, _ = admin_client
    csrf_token = token(client)
    data = {
        "label": "Local mail",
        "settings": {
            "host": "127.0.0.1",
            "port": 1026,
            "username": "",
            "sender": "CareerFlow <test@example.com>",
            "use_tls": False,
            "use_ssl": False,
            "enabled": True,
        },
        "secret": "",
    }
    response = post(client, "/admin/api/config/mail/draft", data, csrf_token)
    assert response.status_code == 201
    unsafe_transport = post(
        client,
        "/admin/api/config/mail/draft",
        data | {"settings": data["settings"] | {"use_tls": True, "use_ssl": True}},
        csrf_token,
    )
    assert unsafe_transport.status_code == 422
    revision_id = response.json["id"]
    assert (
        post(
            client, f"/admin/api/config/mail/{revision_id}/publish", {"confirm": True}, csrf_token
        ).status_code
        == 200
    )
    email = f"admin-mail-{uuid4().hex}@example.com"
    with mysql_app.app_context():
        assert admin_config.runtime_mail()["revision_id"] == revision_id
        auth.send_registration_code(email)
        record = db.session.scalar(
            select(EmailVerificationCode).where(EmailVerificationCode.email == email)
        )
        assert record is not None
        db.session.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.email == email)
        )
        db.session.commit()


def test_bootstrap_first_admin_generates_private_credentials(mysql_app, tmp_path):
    mysql_app.instance_path = str(tmp_path)
    email = f"bootstrap-{uuid4().hex}@example.com"
    try:
        result = mysql_app.test_cli_runner().invoke(args=["bootstrap-admin", email])
        assert result.exit_code == 0, result.output
        content = (tmp_path / "admin-first-login.txt").read_text(encoding="utf-8")
        password = content.split("Temporary password: ", 1)[1].strip()
        with mysql_app.app_context():
            user = auth.authenticate(email, password)
            assert user.is_admin
        again = mysql_app.test_cli_runner().invoke(args=["bootstrap-admin", email])
        assert again.exit_code != 0
    finally:
        with mysql_app.app_context():
            user = db.session.scalar(select(User).where(User.email == email))
            if user:
                db.session.execute(delete(AdminAudit).where(AdminAudit.actor_id == user.id))
                db.session.delete(user)
                db.session.commit()


def test_bootstrap_preserves_existing_credential_file(mysql_app, tmp_path):
    mysql_app.instance_path = str(tmp_path)
    path = tmp_path / "admin-first-login.txt"
    path.write_text("existing-local-secret", encoding="utf-8")
    email = f"blocked-{uuid4().hex}@example.com"
    result = mysql_app.test_cli_runner().invoke(args=["bootstrap-admin", email])
    assert result.exit_code != 0
    assert path.read_text(encoding="utf-8") == "existing-local-secret"
    with mysql_app.app_context():
        assert db.session.scalar(select(User.id).where(User.email == email)) is None


def test_prompt_publish_rollback_and_quote_pinning(mysql_app, admin_client, context):
    client, _ = admin_client
    csrf_token = token(client)
    uid, _, _, did = context
    category = "prompt_diagnosis"
    settings = {
        "instructions": "请优先解释岗位硬性要求的证据，并标记不确定信息。",
        "output_schema": "diagnosis-v1",
        "variables": ["document", "jd", "answers", "kind", "rounds"],
        "enabled": True,
    }
    assert client.get("/admin/settings").status_code == 200
    invalid = post(
        client,
        f"/admin/api/config/{category}/draft",
        {"label": "无效", "settings": settings | {"output_schema": "arbitrary-code"}},
        csrf_token,
    )
    assert invalid.status_code == 422
    first = post(
        client,
        f"/admin/api/config/{category}/draft",
        {"label": "诊断版一", "settings": settings},
        csrf_token,
    )
    assert first.status_code == 201
    one = first.json["id"]
    assert (
        post(
            client, f"/admin/api/config/{category}/{one}/publish", {"confirm": True}, csrf_token
        ).status_code
        == 200
    )
    with mysql_app.app_context():
        operation = make_operation(uid, did)
        assert operation.input_snapshot["prompt_revision_id"] == one
        assert settings["instructions"] == operation.input_snapshot["prompt_instructions"]
    second = post(
        client,
        f"/admin/api/config/{category}/draft",
        {
            "label": "诊断版二",
            "settings": settings | {"instructions": "请先列出证据，再说明每项评分的不确定性。"},
        },
        csrf_token,
    )
    two = second.json["id"]
    assert (
        post(
            client, f"/admin/api/config/{category}/{two}/publish", {"confirm": True}, csrf_token
        ).status_code
        == 200
    )
    with mysql_app.app_context():
        from app.services.errors import BusinessError

        with pytest.raises(BusinessError, match="重新预估"):
            diagnosis.confirm(uid, operation.id)
        db.session.rollback()
    rolled = post(
        client,
        f"/admin/api/config/{category}/rollback",
        {"revision_id": one, "confirm": True},
        csrf_token,
    )
    assert rolled.status_code == 200
    assert rolled.json["settings"]["instructions"] == settings["instructions"]


def test_model_routes_choose_analysis_and_report(mysql_app, admin_client, context):
    client, _ = admin_client
    csrf_token = token(client)
    uid, _, _, did = context
    category = "model_routes"
    draft = post(
        client,
        f"/admin/api/config/{category}/draft",
        {
            "label": "按任务选择模型",
            "settings": {
                "routes": {"analysis": "analysis-model", "report": "report-model"},
                "enabled": True,
            },
        },
        csrf_token,
    )
    assert draft.status_code == 201
    assert (
        post(
            client,
            f"/admin/api/config/{category}/{draft.json['id']}/publish",
            {"confirm": True},
            csrf_token,
        ).status_code
        == 200
    )
    with mysql_app.app_context():
        analysis = make_operation(uid, did, "analysis")
        report = make_operation(uid, did, "report")
        assert analysis.input_snapshot["model"] == "analysis-model"
        assert report.input_snapshot["model"] == "report-model"
        assert analysis.input_snapshot["model_route_revision_id"] == draft.json["id"]
    bad = post(
        client,
        f"/admin/api/config/{category}/draft",
        {"label": "非法任务", "settings": {"routes": {"shell": "x"}, "enabled": True}},
        csrf_token,
    )
    assert bad.status_code == 422
