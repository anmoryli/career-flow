from app.services.commerce import mock_enabled


def test_mock_checkout_requires_explicit_development_or_test_flag(app):
    with app.app_context():
        app.config.update(APP_ENV="development", MOCK_PAYMENT_ENABLED=False)
        assert not mock_enabled()
        app.config["MOCK_PAYMENT_ENABLED"] = True
        assert mock_enabled()
        app.config["APP_ENV"] = "production"
        assert not mock_enabled()
