from functools import wraps
from urllib.parse import urlsplit
from uuid import uuid4

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import and_, delete, func, or_, select

from app.extensions import db
from app.models import Conversation, ConversationMemory, ConversationMessage, utcnow
from app.schemas import (
    AccountDeleteInput,
    ChangePasswordInput,
    ConversationInput,
    EmailInput,
    LoginInput,
    MemoryInput,
    MessageInput,
    PasswordResetInput,
    ProfileInput,
    RegisterInput,
    ThemeInput,
)
from app.services import auth
from app.services.conversations import append_message, owned_conversation, save_memory
from app.services.errors import BusinessError
from app.services.infrastructure import rate_limit, readiness

web = Blueprint("web", __name__)


def input_data():
    if request.is_json:
        return request.get_json()
    return {key: value for key, value in request.form.items() if key != "csrf_token"}


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return {"error": "login_required", "login_required": True}, 401
            return redirect(url_for("web.login"), code=303)
        return view(*args, **kwargs)

    return wrapper


def set_session(user):
    if request.cookies.get("cf_session"):
        auth.revoke_session(request.cookies["cf_session"])
    token = auth.issue_session(user)
    session.clear()
    target = request.args.get("next") or (request.get_json(silent=True) or {}).get("next")
    parsed_target = urlsplit(target or "")
    if (
        not target
        or not target.startswith("/")
        or target.startswith("//")
        or "\\" in target
        or parsed_target.scheme
        or parsed_target.netloc
    ):
        target = url_for("web.workspace")
    response = (
        jsonify({"authenticated": True, "next": target})
        if request.is_json
        else redirect(target, code=303)
    )
    from flask import current_app

    response.set_cookie(
        "cf_session",
        token,
        max_age=30 * 86400,
        httponly=True,
        secure=current_app.config["SESSION_COOKIE_SECURE"],
        samesite="Lax",
    )
    return response


@web.get("/health/live")
def live():
    return {"status": "alive", "version": "V1"}


@web.get("/health/ready")
def ready():
    checks = readiness()
    return {"status": "ready" if all(checks.values()) else "unavailable"}, (
        200 if all(checks.values()) else 503
    )


@web.get("/")
def home():
    return render_template("home.html")


@web.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        if g.user:
            return redirect(url_for("web.workspace"), code=303)
        return redirect(
            url_for("web.home", auth="register", next=request.args.get("next", "/workspace"))
        )
    rate_limit("registration-ip", request.remote_addr or "unknown", 20, 600)
    data = RegisterInput.model_validate(input_data())
    user = auth.register(data)
    return set_session(user)


@web.post("/auth/code")
def send_code():
    rate_limit("code-ip", request.remote_addr or "unknown", 10, 600)
    data = EmailInput.model_validate(input_data())
    rate_limit("code-email", data.email, 1, 60)
    auth.send_registration_code(data.email)
    if request.is_json:
        return {"message": "若邮箱可以注册，验证码已发送，请检查收件箱。", "retry_after": 60}
    flash("若邮箱可以注册，验证码已发送，请检查收件箱。", "success")
    return redirect(url_for("web.register"), code=303)


@web.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if not g.user:
            return redirect(
                url_for("web.home", auth="login", next=request.args.get("next", "/workspace"))
            )
        return redirect(url_for("web.workspace"), code=303)
    rate_limit("login-ip", request.remote_addr or "unknown", 30, 600)
    data = LoginInput.model_validate(input_data())
    rate_limit("login-email", data.email, 10, 600)
    user = auth.authenticate(data.email, data.password)
    return set_session(user)


@web.get("/password/reset")
def password_reset_page():
    return render_template("password_reset.html")


@web.post("/password/reset/code")
def password_reset_code():
    rate_limit("reset-ip", request.remote_addr or "unknown", 10, 600)
    data = EmailInput.model_validate(input_data())
    rate_limit("reset-email", data.email, 1, 60)
    auth.send_password_reset_code(data.email)
    message = "如果该邮箱已有账号，验证码已发送，请检查收件箱。"
    if request.is_json:
        return {"message": message, "retry_after": 60}
    flash(message, "success")
    return redirect(url_for("web.password_reset_page"), code=303)


@web.post("/password/reset")
def password_reset_submit():
    rate_limit("reset-confirm-ip", request.remote_addr or "unknown", 20, 600)
    data = PasswordResetInput.model_validate(input_data())
    auth.reset_password(data)
    session.clear()
    response = redirect(url_for("web.login"), code=303)
    response.delete_cookie("cf_session", httponly=True, samesite="Lax")
    flash("密码已重置，请重新登录。", "success")
    return response


@web.post("/logout")
@login_required
def logout():
    auth.revoke_session(request.cookies.get("cf_session", ""))
    session.clear()
    response = redirect(url_for("web.home"), code=303)
    response.delete_cookie("cf_session", httponly=True, samesite="Lax")
    return response


@web.get("/workspace")
def workspace():
    from app.models import (
        AIOperation,
        CommerceOrder,
        Diagnostic,
        JobTarget,
        Membership,
        Resume,
    )
    from app.services import commerce
    from app.services.career import owned, serialize_resume

    view = request.args.get("view", "dashboard")
    if g.user is None:
        if view not in {"resume-new", "resume-template", "resume-import", "jobs"}:
            return redirect(url_for("web.home", auth="login", next=request.full_path.rstrip("?")))
        from types import SimpleNamespace

        guest_entitlements = SimpleNamespace(
            resume_count=0, resume_limit=10, free_resume_limit=2,
            can_create_resume=True, can_export_resume=False,
            is_member=False, plan_name="免费版", expires_at=None,
            resume_ai_remaining=5,
        )
        return render_template(
            "workspace.html", conversations=[], count=0, resumes=[], jobs=[], saved_jobs=[],
            current_resume=None, reports=[], completed_reports=[], active_jobs=[],
            active_job_ids=set(), inactive_saved_jobs=[], recent_only_jobs=[],
            entitlements=guest_entitlements,
            membership=None, orders=[], commerce_plans={}, mock_payment_enabled=False,
            uuid4=uuid4, now=utcnow(),
        )
    billing = view == "billing"
    resumes = db.session.scalars(
        select(Resume)
        .where(Resume.user_id == g.user.id)
        .order_by(Resume.updated_at.desc())
        .limit(100)
    ).all()
    jobs = db.session.scalars(
        select(JobTarget)
        .where(JobTarget.user_id == g.user.id)
        .order_by(JobTarget.id.desc())
        .limit(100)
    ).all()
    saved_jobs = [item for item in jobs if item.is_saved]
    active_job_rows = db.session.execute(
        select(AIOperation, Diagnostic, JobTarget)
        .join(Diagnostic, AIOperation.diagnostic_id == Diagnostic.id)
        .join(JobTarget, Diagnostic.job_id == JobTarget.id)
        .where(
            AIOperation.user_id == g.user.id,
            AIOperation.state.in_(["queued", "running"]),
        )
        .order_by(AIOperation.id.desc())
    ).all()
    active_jobs = []
    seen_active_job_ids = set()
    for row in active_job_rows:
        if row[2].id not in seen_active_job_ids:
            active_jobs.append(row)
            seen_active_job_ids.add(row[2].id)
    active_job_ids = {job.id for _, _, job in active_jobs}
    inactive_saved_jobs = [job for job in saved_jobs if job.id not in active_job_ids]
    recent_only_jobs = [job for job in jobs if not job.is_saved and job.id not in active_job_ids]
    resume_id = request.args.get("resume_id", type=int)
    current_resume = serialize_resume(owned(Resume, g.user.id, resume_id)) if resume_id else None
    reports = db.session.execute(
        select(AIOperation, Diagnostic, JobTarget)
        .join(Diagnostic, AIOperation.diagnostic_id == Diagnostic.id)
        .join(JobTarget, Diagnostic.job_id == JobTarget.id)
        .where(
            AIOperation.user_id == g.user.id,
            or_(
                and_(
                    AIOperation.kind == "report",
                    AIOperation.state.in_(
                        ["queued", "running", "succeeded", "failed", "cancelled"]
                    ),
                ),
                AIOperation.state.in_(["queued", "running"]),
            ),
        )
        .order_by(AIOperation.id.desc())
        .limit(100)
    ).all()
    completed_reports = [row for row in reports if row[0].state == "succeeded"]
    membership = db.session.get(Membership, g.user.id) if billing else None
    orders = (
        db.session.scalars(
            select(CommerceOrder)
            .where(CommerceOrder.user_id == g.user.id)
            .order_by(CommerceOrder.id.desc())
            .limit(50)
        ).all()
        if billing
        else []
    )
    entitlements = commerce.entitlements(g.user.id)
    mock_payment_enabled = commerce.mock_enabled()
    conversations = db.session.scalars(
        select(Conversation)
        .where(
            Conversation.user_id == g.user.id,
        )
        .order_by(Conversation.id.desc())
        .limit(100)
    ).all()
    count = db.session.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.user_id == g.user.id,
        )
    )
    return render_template(
        "workspace.html",
        conversations=conversations,
        count=count,
        resumes=resumes,
        jobs=jobs,
        saved_jobs=saved_jobs,
        active_jobs=active_jobs,
        active_job_ids=active_job_ids,
        inactive_saved_jobs=inactive_saved_jobs,
        recent_only_jobs=recent_only_jobs,
        current_resume=current_resume,
        reports=reports,
        completed_reports=completed_reports,
        entitlements=entitlements,
        membership=membership,
        orders=orders,
        commerce_plans=commerce.PLANS if billing else None,
        mock_payment_enabled=mock_payment_enabled,
        uuid4=uuid4,
        now=utcnow(),
    )


@web.post("/settings/theme")
@login_required
def theme():
    data = ThemeInput.model_validate(input_data())
    g.user.theme = data.theme
    db.session.commit()
    return {"theme": data.theme}


@web.post("/settings/profile")
@login_required
def profile():
    data = ProfileInput.model_validate(input_data())
    g.user.display_name = data.display_name
    db.session.commit()
    flash("个人信息已更新。", "success")
    return redirect(url_for("web.workspace", view="settings"), code=303)


@web.post("/sessions/revoke")
@login_required
def revoke_sessions():
    auth.revoke_all_sessions(g.user.id)
    session.clear()
    response = redirect(url_for("web.login"), code=303)
    response.delete_cookie("cf_session")
    return response


@web.post("/settings/password")
@login_required
def change_password():
    rate_limit("password-change", str(g.user.id), 5, 600)
    auth.change_password(g.user.id, ChangePasswordInput.model_validate(input_data()))
    session.clear()
    response = redirect(url_for("web.login"), code=303)
    response.delete_cookie("cf_session", httponly=True, samesite="Lax")
    flash("密码已更新，请重新登录。", "success")
    return response


@web.post("/settings/delete")
@login_required
def delete_account():
    rate_limit("account-delete", str(g.user.id), 3, 600)
    auth.delete_account(g.user.id, AccountDeleteInput.model_validate(input_data()))
    session.clear()
    response = redirect(url_for("web.home"), code=303)
    response.delete_cookie("cf_session", httponly=True, samesite="Lax")
    flash("账号与全部个人数据已永久删除。", "success")
    return response


@web.post("/conversations")
@login_required
def create_conversation():
    data = ConversationInput.model_validate(input_data())
    item = Conversation(user_id=g.user.id, title=data.title)
    db.session.add(item)
    db.session.commit()
    return redirect(url_for("web.conversation", conversation_id=item.id), code=303)


@web.get("/conversations/<int:conversation_id>")
@login_required
def conversation(conversation_id):
    item = owned_conversation(g.user.id, conversation_id)
    messages = db.session.scalars(
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == item.id,
        )
        .order_by(ConversationMessage.id)
        .limit(500)
    ).all()
    memories = db.session.scalars(
        select(ConversationMemory)
        .where(
            ConversationMemory.conversation_id == item.id,
        )
        .order_by(ConversationMemory.id)
        .limit(100)
    ).all()
    return render_template(
        "conversation.html",
        conversation=item,
        messages=messages,
        memories=memories,
        request_key=str(uuid4()),
    )


@web.post("/conversations/<int:conversation_id>/messages")
@login_required
def message(conversation_id):
    data = MessageInput.model_validate(input_data())
    append_message(g.user.id, conversation_id, data)
    # Explicitly persist a user note, never impersonate an unconfigured AI provider.
    return redirect(url_for("web.conversation", conversation_id=conversation_id), code=303)


@web.post("/conversations/<int:conversation_id>/memories")
@login_required
def memory(conversation_id):
    data = MemoryInput.model_validate(input_data())
    save_memory(g.user.id, conversation_id, data)
    return redirect(url_for("web.conversation", conversation_id=conversation_id), code=303)


@web.post("/conversations/<int:conversation_id>/delete")
@login_required
def delete_conversation(conversation_id):
    from app.models import Diagnostic

    item = owned_conversation(g.user.id, conversation_id, lock=True)
    if db.session.scalar(select(Diagnostic.id).where(Diagnostic.conversation_id == item.id)):
        raise BusinessError("此记录关联岗位诊断，不能单独删除。", 409)
    if request.form.get("confirm") != "delete":
        raise BusinessError("请确认永久删除此对话。")
    db.session.execute(delete(Conversation).where(Conversation.id == item.id))
    db.session.commit()
    flash("对话与关联消息、记忆已永久删除。", "success")
    return redirect(url_for("web.workspace"), code=303)
