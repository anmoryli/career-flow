import os
from uuid import uuid4

import pytest

from app import create_app


@pytest.fixture
def config():
    return {
        "APP_ENV": "testing",
        "TESTING": True,
        "SECRET_KEY": "unit-test-secret-" + "a" * 40,
        "SESSION_ENCRYPTION_KEY": "unit-test-hmac-" + "b" * 40,
        "SQLALCHEMY_DATABASE_URI": (
            "mysql+pymysql://test@127.0.0.1:1/careerflow_test?charset=utf8mb4"
        ),
        "REDIS_URL": "redis://127.0.0.1:1/15",
        "RATE_LIMIT_NAMESPACE": f"careerflow:test:{uuid4().hex}",
    }


@pytest.fixture
def app(config):
    application = create_app(config)
    yield application
    from app.extensions import db

    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def mysql_app(config):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated MySQL 8.4 test database")
    from sqlalchemy.engine import make_url

    if make_url(url).database != "careerflow_test":
        pytest.fail("Integration database must be named careerflow_test")
    config.update(
        {
            "SQLALCHEMY_DATABASE_URI": url,
            "REDIS_URL": os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6390/15"),
            "MAIL_SERVER": "127.0.0.1",
            "MAIL_PORT": 1026,
        }
    )
    application = create_app(config)
    yield application
    from app.extensions import db

    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def user_factory(mysql_app):
    from sqlalchemy import delete
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import AuthIdentity, User

    created = []

    def create():
        with mysql_app.app_context():
            user = User(email=f"test-{uuid4().hex}@example.com", display_name="测试用户 中文 🟢")
            db.session.add(user)
            db.session.flush()
            db.session.add(
                AuthIdentity(
                    user_id=user.id,
                    password_hash=generate_password_hash("valid-test-password"),
                )
            )
            db.session.commit()
            created.append(user.id)
            return user.id, user.email

    yield create
    with mysql_app.app_context():
        db.session.execute(delete(User).where(User.id.in_(created)))
        db.session.commit()
