import json
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
        "fallback_model_ids": ["test-fallback-1", "test-fallback-2"],
        "base_url": "https://models.example.com/v1",
        "tokens_per_credit": 1000,
        "enabled": True,
    } | changes


def test_membership_prices_are_fixed_in_product_configuration(mysql_app, admin_client):
    client, _ = admin_client
    page = client.get("/admin/settings")
    assert page.status_code == 200
    assert "commerce" not in page.text
    assert "积分" not in page.text
    assert "积分包" not in page.text

    from app.services.commerce import PLANS

    assert PLANS["membership_monthly"]["price_yuan"] == Decimal("39.00")
    assert PLANS["membership_quarterly"]["price_yuan"] == Decimal("99.00")


def test_admin_access_and_model_secret_lifecycle(mysql_app, user_factory, admin_client):
    client, uid = admin_client
    anonymous = mysql_app.test_client()
    ordinary_uid, _ = user_factory()
    ordinary, _ = login_client(mysql_app, ordinary_uid)
    assert anonymous.get("/admin").status_code == 303
    anonymous_api = anonymous.get("/admin/api/config/model")
    assert anonymous_api.status_code == 401 and anonymous_api.is_json
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


def test_three_model_profiles_use_independent_providers_and_secrets(mysql_app, admin_client):
    client, _ = admin_client
    csrf_token = token(client)
    profiles = [
        {"provider": "DeepSeek", "model_id": "deepseek-chat", "base_url": "https://api.deepseek.com/v1"},
        {"provider": "OpenAI", "model_id": "gpt-4.1-mini", "base_url": "https://api.openai.com/v1"},
        {"provider": "Qwen", "model_id": "qwen-plus", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    ]
    secret_values = ["deepseek-test-key", "openai-test-key", "qwen-test-key"]
    draft = post(
        client,
        "/admin/api/config/model/activate",
        {
            "label": "独立三模型",
            "settings": {"models": profiles, "enabled": True, "tokens_per_credit": None},
            "secret": json.dumps(secret_values),
        },
        csrf_token,
    )
    assert draft.status_code == 200
    assert all(secret not in draft.text for secret in secret_values)
    revision_id = draft.json["id"]
    assert draft.json["state"] == "published"
    with mysql_app.app_context():
        for profile, secret in zip(profiles, secret_values, strict=True):
            runtime = admin_config.runtime_model_profile(revision_id, profile["model_id"])
            assert runtime["provider"] == profile["provider"]
            assert runtime["base_url"] == profile["base_url"]
            assert runtime["secret"] == secret
            assert runtime["enabled"] is True
            assert runtime["revision_id"] == revision_id


def test_admin_api_business_errors_are_json(mysql_app, admin_client):
    client, _ = admin_client
    response = client.get("/admin/api/config/not-a-category")
    assert response.status_code == 404
    assert response.is_json
    assert response.json["error"] == "未知配置类别。"


def test_service_configuration_shows_current_values_without_history_controls(
    mysql_app, admin_client
):
    client, _ = admin_client
    page = client.get("/admin/settings")
    assert page.status_code == 200
    assert "保存并启用" in page.text
    assert "保存草稿" not in page.text
    assert "回滚到此版本" not in page.text
    assert 'name="model_provider_1"' in page.text
    assert 'name="model_provider_2"' in page.text
    assert 'name="model_provider_3"' in page.text


def test_old_single_model_revision_does_not_break_configuration_page(mysql_app, admin_client):
    client, uid = admin_client
    with mysql_app.app_context():
        db.session.add(
            ConfigRevision(
                category="model",
                version=1,
                label="旧版单模型",
                settings={
                    "provider": "Legacy",
                    "model_id": "legacy-chat",
                    "fallback_model_ids": [],
                    "base_url": "https://models.example.com/v1",
                    "enabled": True,
                },
                encrypted_secret="legacy-encrypted-secret",
                state="published",
                author_id=uid,
            )
        )
        db.session.commit()
    page = client.get("/admin/settings")
    assert page.status_code == 200


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
        with mysql_app.app_context():
            has_admin = (
                db.session.scalar(select(User.id).where(User.is_admin.is_(True))) is not None
            )
        result = mysql_app.test_cli_runner().invoke(args=["bootstrap-admin", email])
        if has_admin:
            assert result.exit_code != 0
            assert "already exists" in result.output
            assert not (tmp_path / "admin-first-login.txt").exists()
        else:
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

        with pytest.raises(BusinessError, match="配置已更新"):
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
