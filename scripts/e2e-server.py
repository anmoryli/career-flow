"""Isolated browser fixture server. Never import this module from application code."""

import sys
import threading
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import dotenv_values
from flask import jsonify, request
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from app import create_app
from app.extensions import db
from app.models import ActiveConfig, AdminAudit, CommerceOrder, ConfigRevision, User
from app.services import auth, diagnosis

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root / ".env")
url = make_url(values["DATABASE_URL"]).set(database="careerflow_test")
assert url.host == "127.0.0.1" and url.database == "careerflow_test"
app = create_app(
    {
        "APP_ENV": "testing",
        "TESTING": True,
        "SECRET_KEY": "e2e-only-" + "a" * 40,
        "SESSION_ENCRYPTION_KEY": "e2e-hmac-" + "b" * 40,
        "SQLALCHEMY_DATABASE_URI": url.render_as_string(hide_password=False),
        "REDIS_URL": "redis://127.0.0.1:6390/15",
        "ADMIN_CONFIG_KEY": "browser-only-admin-key-" + "c" * 48,
        "MOCK_PAYMENT_ENABLED": True,
        "RATE_LIMIT_NAMESPACE": f"careerflow:e2e:{uuid4().hex}",
    }
)
created = set()


def fixture_provider(snapshot):
    names = ["技能匹配", "岗位职责", "工作与项目经历", "成果与影响力", "学历及其他条件"]
    document = snapshot["document"]
    suggestions = [
        {
            "path": "summary",
            "original": document["summary"],
            "proposed": document["summary"] + "。",
            "reason": "补充标点",
        }
    ]
    experiences = document.get("experiences", [])
    bullets = experiences[0].get("bullets", []) if experiences else []
    if bullets:
        suggestions.append(
            {
                "path": "experiences.0.bullets.0",
                "original": bullets[0],
                "proposed": bullets[0] + "。",
                "reason": "在已有工作内容后补齐标点",
            }
        )
    return {
        "summary": "开发测试结果，非真实模型输出",
        "dimensions": [{"name": name, "score": 60, "reason": "仅用于测试渲染"} for name in names],
        "findings": [
            {
                "requirement": snapshot["jd"][:20],
                "category": "missing",
                "source": "none",
                "evidence": "",
                "explanation": "待用户确认",
            }
        ],
        "suggestions": suggestions,
        "question": "可以补充一个真实项目吗？",
    }, 1000


app.extensions["diagnosis_provider"] = fixture_provider
app.extensions["resume_provider"] = lambda snapshot: (
    {"proposed": (snapshot["original"] or "已提供的背景") + "，表达更清晰", "reason": "仅整理原文"},
    1000,
)
app.extensions["resume_compose_provider"] = lambda snapshot: (
    {
        "document": {
            "name": "林测试",
            "role": "产品经理",
            "summary": "负责产品需求分析",
            "experiences": [{"company": "示例公司", "bullets": ["负责产品需求分析"]}],
        },
        "reason": "仅用于浏览器测试，请核对原文",
    },
    1000,
)


class TestQueue:
    def __init__(self, *args, **kwargs):
        pass

    def enqueue(self, function, operation_id, **kwargs):
        def run():
            with app.app_context():
                if function == "app.jobs.pdf_import_job":
                    from app.services.pdf_import import run_import

                    run_import(operation_id)
                elif function == "app.jobs.resume_ai_job":
                    from app.services.resume_ai import run_operation

                    run_operation(operation_id)
                else:
                    diagnosis.run_operation(operation_id)

        threading.Thread(target=run, daemon=True).start()


import app.web.career as career_routes  # noqa: E402
import app.web.diagnosis as diagnosis_routes  # noqa: E402
import app.web.imports as imports_routes  # noqa: E402

diagnosis_routes.Queue = TestQueue
imports_routes.Queue = TestQueue
career_routes.Queue = TestQueue


@app.post("/__test/session")
def test_session():
    user = User(email=f"browser-{uuid4().hex}@example.com", display_name="浏览器测试")
    db.session.add(user)
    db.session.commit()
    created.add(user.id)
    password = (request.get_json(silent=True) or {}).get("password")
    if password:
        from werkzeug.security import generate_password_hash

        from app.models import AuthIdentity

        identity = AuthIdentity(user_id=user.id, password_hash=generate_password_hash(password))
        db.session.add(identity)
        db.session.commit()
    response = jsonify({"user_id": user.id, "email": user.email, "test_mode": True})
    response.set_cookie("cf_session", auth.issue_session(user), httponly=True, samesite="Lax")
    return response


@app.post("/__test/cleanup")
def cleanup():
    user_id = request.json["user_id"]
    if user_id not in created:
        return {}, 404
    revisions = db.session.scalars(
        select(ConfigRevision.id).where(ConfigRevision.author_id == user_id)
    ).all()
    db.session.execute(delete(CommerceOrder).where(CommerceOrder.user_id == user_id))
    if revisions:
        db.session.execute(delete(ActiveConfig).where(ActiveConfig.revision_id.in_(revisions)))
    db.session.execute(delete(AdminAudit).where(AdminAudit.actor_id == user_id))
    db.session.execute(delete(ConfigRevision).where(ConfigRevision.author_id == user_id))
    db.session.execute(delete(User).where(User.id == user_id))
    db.session.commit()
    created.remove(user_id)
    return {"deleted": True}


@app.post("/__test/promote")
def promote():
    user_id = request.json["user_id"]
    if user_id not in created:
        return {}, 404
    db.session.get(User, user_id).is_admin = True
    db.session.commit()
    return {"admin": True}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8011, threaded=True, use_reloader=False)
