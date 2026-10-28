import pytest
from pydantic import ValidationError
from redis.exceptions import RedisError

from app.config import load_config
from app.diagnosis_schemas import AnswerInput
from app.services import infrastructure
from app.services.errors import BusinessError


@pytest.mark.parametrize(
    "changes",
    [
        {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"},
        {"APP_ENV": "unknown"},
        {"SECRET_KEY": "short"},
    ],
)
def test_invalid_configuration_rejected(config, changes):
    with pytest.raises(ValueError):
        load_config(config | changes)


def test_production_response_headers_and_error_redaction(app):
    @app.get("/test-error")
    def fail():
        raise RuntimeError("private-credentials-never-returned")

    app.config.update(TESTING=False, APP_ENV="production")
    response = app.test_client().get("/test-error", json={})
    assert response.status_code == 500
    assert "private-credentials" not in response.text
    assert response.json["request_id"]
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"


def test_rate_service_unavailable_is_explicit(app, monkeypatch):
    class BrokenRedis:
        def eval(self, *args):
            raise RedisError("not-for-client")

    monkeypatch.setattr(infrastructure, "redis_client", BrokenRedis)
    with app.app_context(), pytest.raises(BusinessError, match="暂不可用"):
        infrastructure.rate_limit("test", "identity", 1, 60)


def test_empty_answer_must_be_explicit_skip():
    with pytest.raises(ValidationError):
        AnswerInput(request_key="00000000-0000-4000-8000-000000000001", revision=0, answer=" ")


def test_testing_mode_raises_unexpected_errors(app):
    @app.get("/test-programming-error")
    def fail():
        raise RuntimeError("programming error")

    with pytest.raises(RuntimeError):
        app.test_client().get("/test-programming-error")


def test_complete_production_configuration_passes_guards(config):
    result = load_config(
        config
        | {
            "APP_ENV": "production",
            "MOCK_PAYMENT_ENABLED": False,
            "SESSION_COOKIE_SECURE": True,
            "MAIL_USE_TLS": True,
            "MAIL_USERNAME": "test-user",
            "SQLALCHEMY_DATABASE_URI": config["SQLALCHEMY_DATABASE_URI"] + "&ssl_ca=/test/ca.pem",
        }
    )
    assert result["APP_ENV"] == "production"


def test_static_assets_keep_cache_policy_and_security_headers(app):
    response = app.test_client().get("/static/js/theme.js")
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") != "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
