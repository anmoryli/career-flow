import hashlib

from flask import current_app
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.services.errors import BusinessError


def redis_client() -> Redis:
    return current_app.extensions["redis"]


def rate_limit(scope: str, identity: str, limit: int, seconds: int) -> None:
    namespace = current_app.config.get("RATE_LIMIT_NAMESPACE", "careerflow:limit")
    key = f"{namespace}:{scope}:{hashlib.sha256(identity.encode()).hexdigest()}"
    script = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    return count
    """
    try:
        count = redis_client().eval(script, 1, key, seconds)
    except RedisError:
        raise BusinessError("请求保护服务暂不可用，请稍后重试。", 503) from None
    if count > limit:
        raise BusinessError("操作过于频繁，请稍后重试。", 429)


def readiness() -> dict[str, bool]:
    checks = {"mysql": False, "schema": False, "redis": False}
    try:
        with db.engine.connect() as connection:
            version = connection.scalar(text("SELECT VERSION()"))
            checks["mysql"] = version.startswith("8.4.")
            database_heads = set(
                connection.scalars(text("SELECT version_num FROM alembic_version"))
            )
            from alembic.script import ScriptDirectory

            migration = current_app.extensions["migrate"].migrate
            expected_heads = set(ScriptDirectory.from_config(migration.get_config()).get_heads())
            checks["schema"] = bool(expected_heads) and database_heads == expected_heads
    except SQLAlchemyError:
        pass
    try:
        checks["redis"] = bool(redis_client().ping())
    except RedisError:
        pass
    return checks
