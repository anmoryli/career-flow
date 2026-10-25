import logging
import uuid

from flask import Flask, g, render_template, request
from pydantic import ValidationError
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.config import load_config
from app.extensions import csrf, db, migrate
from app.services.errors import BusinessError
from app.services.resume_markdown import inline_markdown, resume_markdown


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.jinja_env.filters["resume_markdown"] = resume_markdown
    app.jinja_env.filters["resume_markdown_inline"] = inline_markdown
    app.config.update(load_config(overrides))
    db.init_app(app)
    migrate.init_app(app, db)
    app.extensions["redis"] = Redis.from_url(
        app.config["REDIS_URL"],
        socket_connect_timeout=2,
        socket_timeout=2,
        retry=Retry(NoBackoff(), 0),
    )
    from app import models  # noqa: F401
    from app.cli import register_commands
    from app.web.routes import web

    app.register_blueprint(web)
    from app.web.career import career_web

    app.register_blueprint(career_web)
    from app.web.diagnosis import diagnosis_web

    app.register_blueprint(diagnosis_web)
    from app.web.commerce import commerce_web

    app.register_blueprint(commerce_web)
    from app.web.imports import imports_web

    app.register_blueprint(imports_web)
    from app.web.admin import admin_web

    app.register_blueprint(admin_web)
    register_commands(app)

    @app.before_request
    def request_context():
        g.request_id = uuid.uuid4().hex
        g.user = None
        if request.path.startswith("/static/") or request.path.startswith("/health/"):
            return
        from app.services.auth import resolve_session

        g.user = resolve_session(request.cookies.get("cf_session", ""))
        if g.user and request.method == "POST" and request.path.startswith("/api/"):
            from app.services.infrastructure import rate_limit

            rate_limit("business-write", str(g.user.id), 240, 60)

    csrf.init_app(app)

    @app.after_request
    def secure_response(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", uuid.uuid4().hex)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'; object-src 'none'"
        )
        if app.config["APP_ENV"] == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def error_response(message: str, status: int, field_errors=None):
        db.session.rollback()
        if request.is_json or request.path.startswith("/health/"):
            body = {"error": message, "request_id": getattr(g, "request_id", "")}
            if field_errors:
                body["fields"] = field_errors
            return body, status
        return render_template("error.html", message=message, status=status), status

    @app.errorhandler(BusinessError)
    def business_error(error):
        return error_response(str(error), error.status)

    @app.errorhandler(ValidationError)
    def validation_error(error):
        fields = ", ".join(
            sorted({str(item["loc"][0]) if item["loc"] else "表单" for item in error.errors()})
        )
        labels = {
            "email": "邮箱",
            "password": "密码",
            "current_password": "当前密码",
            "new_password": "新密码",
            "confirm_password": "确认密码",
            "display_name": "称呼",
            "code": "验证码",
            "title": "名称",
            "document": "简历内容",
            "description": "岗位描述",
        }
        errors = {
            str(item["loc"][0]): f"请检查{labels.get(str(item['loc'][0]), '该字段')}的格式与长度。"
            for item in error.errors()
            if item["loc"]
        }
        return error_response(f"请检查填写内容：{fields}", 422, errors)

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        app.logger.error("database_error request_id=%s", getattr(g, "request_id", ""))
        return error_response("数据服务暂不可用，请稍后重试。", 503)

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {
            400: "请求校验失败，请刷新页面后重试。",
            404: "页面不存在。",
            413: "提交内容过大。",
            405: "请求方式不支持。",
        }
        return error_response(messages.get(error.code, "请求未完成。"), error.code)

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if app.testing:
            raise error
        # Never log exception messages: database URLs and SMTP credentials may appear there.
        app.logger.error(
            "internal_error type=%s request_id=%s",
            type(error).__name__,
            getattr(g, "request_id", ""),
        )
        return error_response("服务出现异常，请稍后重试。", 500)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    return app
