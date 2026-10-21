import pytest
from pydantic import ValidationError

from app import create_app
from app.config import boolean, load_config
from app.schemas import MemoryInput, RegisterInput, StructuredMessage, ThemeInput


def test_home_and_headers_without_database(app):
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert "职序" in response.text
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert len(response.headers["X-Request-ID"]) == 32


def test_liveness_does_not_require_database(app):
    response = app.test_client().get("/health/live")
    assert response.status_code == 200
    assert response.json == {"status": "alive", "version": "V1"}


def test_readiness_fails_honestly(app):
    response = app.test_client().get("/health/ready")
    assert response.status_code == 503
    assert "password" not in response.text


def test_csrf_rejects_missing_token(app):
    response = app.test_client().post("/login", data={"email": "x@example.com"})
    assert response.status_code == 400
    assert "校验失败" in response.text


def test_missing_and_method_errors(app):
    assert app.test_client().get("/missing").status_code == 404
    assert app.test_client().get("/logout").status_code == 405


def test_database_failure_redacted(app):
    client = app.test_client()
    client.set_cookie("cf_session", "opaque-token")
    response = client.get("/workspace")
    assert response.status_code == 503
    assert "mysql+pymysql" not in response.text
    assert "opaque-token" not in response.text


@pytest.mark.parametrize(
    "url", ["sqlite://", "postgresql://localhost/test", "mysql+pymysql://localhost/test"]
)
def test_only_mysql_utf8mb4(config, url):
    config["SQLALCHEMY_DATABASE_URI"] = url
    with pytest.raises(ValueError, match="DATABASE_URL"):
        load_config(config)


def test_requires_independent_secrets(config):
    config["SESSION_ENCRYPTION_KEY"] = config["SECRET_KEY"]
    with pytest.raises(ValueError, match="independent"):
        load_config(config)


def test_production_guards(config):
    config.update(APP_ENV="production", MOCK_PAYMENT_ENABLED=True)
    with pytest.raises(ValueError, match="Mock payments"):
        load_config(config)
    config["MOCK_PAYMENT_ENABLED"] = False
    with pytest.raises(ValueError, match="Secure cookies"):
        load_config(config)
    config["SESSION_COOKIE_SECURE"] = True
    with pytest.raises(ValueError, match="TLS mail"):
        load_config(config)
    config.update(MAIL_USERNAME="sender", MAIL_USE_TLS=True)
    with pytest.raises(ValueError, match="MySQL TLS"):
        load_config(config)


def test_factory_isolated(config):
    first = create_app(config)
    second = create_app(config | {"SECRET_KEY": "different" * 8})
    assert first.secret_key != second.secret_key
    assert first.extensions["redis"] is not second.extensions["redis"]


def test_strict_input():
    with pytest.raises(ValidationError):
        ThemeInput(theme="arbitrary")
    with pytest.raises(ValidationError):
        MemoryInput(key="经历", value="推测经历", confirmed="no")
    with pytest.raises(ValidationError):
        StructuredMessage(
            schema_version="1.0",
            message="x",
            conversation_state="active",
            blocks=[{"type": "script", "code": "alert(1)"}],
        )
    with pytest.raises(ValidationError):
        RegisterInput(email="x@example.com", password="short", code="123456", display_name="X")


def test_bool_strict():
    assert boolean("true") is True
    assert boolean("FALSE") is False
    with pytest.raises(ValueError):
        boolean("maybe")
