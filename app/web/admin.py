from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, url_for
from sqlalchemy import func, select

from app.admin_schemas import ConfigDraftInput, ConfigPublishInput, ConfigRollbackInput
from app.extensions import db
from app.models import AdminAudit, AIOperation, CommerceOrder, Membership, User, utcnow
from app.services import admin_config, auth
from app.services.errors import BusinessError
from app.web.routes import input_data

admin_web = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("web.login"), code=303)
        if not g.user.is_admin:
            raise BusinessError("无权访问管理后台。", 403)
        return view(*args, **kwargs)

    return wrapper


@admin_web.get("")
@admin_web.get("/")
@admin_required
def dashboard():
    counts = {
        "users": db.session.scalar(select(func.count()).select_from(User)),
        "ai_calls": db.session.scalar(select(func.count()).select_from(AIOperation)),
        "failed_ai": db.session.scalar(
            select(func.count()).select_from(AIOperation).where(AIOperation.state == "failed")
        ),
        "orders": db.session.scalar(select(func.count()).select_from(CommerceOrder)),
        "members": db.session.scalar(
            select(func.count()).select_from(Membership).where(Membership.expires_at > utcnow())
        ),
    }
    return render_template("admin/dashboard.html", counts=counts)


@admin_web.get("/users")
@admin_required
def users():
    items = db.session.scalars(select(User).order_by(User.created_at.desc()).limit(100)).all()
    return render_template("admin/users.html", users=items)


@admin_web.get("/orders")
@admin_required
def orders():
    items = db.session.execute(
        select(CommerceOrder, User.email)
        .join(User, CommerceOrder.user_id == User.id)
        .order_by(CommerceOrder.id.desc())
        .limit(100)
    ).all()
    return render_template("admin/orders.html", orders=items)


@admin_web.post("/users/<int:user_id>/revoke-sessions")
@admin_required
def revoke_user_sessions(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        raise BusinessError("用户不存在。", 404)
    admin_config.audit(
        g.user.id,
        "revoke_sessions",
        f"user:{user_id}",
        before={"email": target.email},
        after={"sessions": "revoked"},
    )
    auth.revoke_all_sessions(user_id)
    flash(
        f"已撤销 {target.email} 的全部登录会话。",
        "success",
    )
    return redirect(url_for("admin.users"), code=303)


@admin_web.get("/settings")
@admin_required
def settings():
    configurations = {
        category: admin_config.history(category)
        for category in ("mail", "model", "model_routes", "prompt_diagnosis")
    }
    return render_template("admin/settings.html", configurations=configurations)


@admin_web.get("/audit")
@admin_required
def audit():
    items = db.session.scalars(
        select(AdminAudit).order_by(AdminAudit.created_at.desc()).limit(100)
    ).all()
    return render_template("admin/audit.html", entries=items)


@admin_web.get("/api/config/<category>")
@admin_required
def config_history(category):
    return admin_config.history(category)


@admin_web.get("/api/models")
@admin_required
def available_models():
    return admin_config.available_models()


@admin_web.post("/api/config/<category>/draft")
@admin_required
def config_draft(category):
    data = ConfigDraftInput.model_validate(input_data())
    return admin_config.revision_summary(admin_config.create_draft(g.user.id, category, data)), 201


@admin_web.post("/api/config/<category>/<int:revision_id>/publish")
@admin_required
def config_publish(category, revision_id):
    data = ConfigPublishInput.model_validate(input_data())
    return admin_config.revision_summary(
        admin_config.publish(g.user.id, category, revision_id, data.confirm)
    )


@admin_web.post("/api/config/<category>/rollback")
@admin_required
def config_rollback(category):
    data = ConfigRollbackInput.model_validate(input_data())
    return admin_config.revision_summary(
        admin_config.rollback(g.user.id, category, data.revision_id, data.confirm)
    )
