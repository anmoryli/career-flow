import os
from datetime import timedelta

from sqlalchemy.engine import make_url


def boolean(value: str) -> bool:
    if value.lower() not in {"true", "false"}:
        raise ValueError("Boolean configuration must be true or false")
    return value.lower() == "true"


def load_config(overrides: dict | None = None) -> dict:
    config = {
        "APP_ENV": os.getenv("APP_ENV", "development"),
        "SECRET_KEY": os.getenv("SECRET_KEY", ""),
        "SESSION_ENCRYPTION_KEY": os.getenv("SESSION_ENCRYPTION_KEY", ""),
        "SQLALCHEMY_DATABASE_URI": os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://careerflow@127.0.0.1:3310/careerflow?charset=utf8mb4",
        ),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "pool_pre_ping": True,
            "pool_size": int(os.getenv("MYSQL_POOL_SIZE", "5")),
            "pool_recycle": int(os.getenv("MYSQL_POOL_RECYCLE", "1800")),
            "connect_args": {"connect_timeout": 3, "read_timeout": 5, "write_timeout": 5},
        },
        "REDIS_URL": os.getenv("REDIS_URL", "redis://127.0.0.1:6390/0"),
        "MAIL_SERVER": os.getenv("MAIL_SERVER", "127.0.0.1"),
        "MAIL_PORT": int(os.getenv("MAIL_PORT", "1026")),
        "MAIL_USERNAME": os.getenv("MAIL_USERNAME", ""),
        "MAIL_PASSWORD": os.getenv("MAIL_PASSWORD", ""),
        "MAIL_USE_TLS": boolean(os.getenv("MAIL_USE_TLS", "false")),
        "MAIL_DEFAULT_SENDER": os.getenv("MAIL_DEFAULT_SENDER", "noreply@careerflow.local"),
        "SESSION_COOKIE_SECURE": boolean(os.getenv("COOKIE_SECURE", "false")),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": timedelta(days=30),
        "MAX_CONTENT_LENGTH": 5 * 1024 * 1024,
        "MOCK_PAYMENT_ENABLED": boolean(os.getenv("MOCK_PAYMENT_ENABLED", "false")),
        "WTF_CSRF_TIME_LIMIT": 7200,
        "AI_ENABLED": boolean(os.getenv("AI_ENABLED", "false")),
        "AI_MODEL": os.getenv("AI_MODEL", ""),
        "AI_API_KEY": os.getenv("AI_API_KEY", ""),
        "AI_BASE_URL": os.getenv("AI_BASE_URL", "https://api.openai.com/v1"),
        "AI_TOKENS_PER_CREDIT": int(os.getenv("AI_TOKENS_PER_CREDIT", "1000")),
        "ADMIN_CONFIG_KEY": os.getenv("ADMIN_CONFIG_KEY", ""),
    }
    config.update(overrides or {})
    if config["AI_TOKENS_PER_CREDIT"] < 1:
        raise ValueError("AI_TOKENS_PER_CREDIT must be positive")
    url = make_url(config["SQLALCHEMY_DATABASE_URI"])
    if url.drivername != "mysql+pymysql" or url.query.get("charset") != "utf8mb4":
        raise ValueError("DATABASE_URL must use mysql+pymysql and charset=utf8mb4")
    if config["APP_ENV"] not in {"development", "testing", "production"}:
        raise ValueError("Unknown APP_ENV")
    for key in ("SECRET_KEY", "SESSION_ENCRYPTION_KEY"):
        if len(config[key]) < 32 or config[key].startswith("replace-"):
            raise ValueError(f"{key} must be configured with an independent random secret")
    if config["SECRET_KEY"] == config["SESSION_ENCRYPTION_KEY"]:
        raise ValueError("Application secrets must be independent")
    if config["APP_ENV"] == "production":
        if config["MOCK_PAYMENT_ENABLED"]:
            raise ValueError("Mock payments are disabled in production")
        if not config["SESSION_COOKIE_SECURE"]:
            raise ValueError("Production requires Secure cookies and HTTPS")
        if not config["MAIL_USERNAME"] or not config["MAIL_USE_TLS"]:
            raise ValueError("Production requires authenticated TLS mail")
        if not url.query.get("ssl_ca"):
            raise ValueError("Production requires MySQL TLS with ssl_ca")
    return config
