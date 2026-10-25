from functools import wraps
from uuid import uuid4

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import delete, func, select

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
            return redirect(url_for("web.login"), code=303)
        return view(*args, **kwargs)

    return wrapper


def set_session(user):
    if request.cookies.get("cf_session"):
        auth.revoke_session(request.cookies["cf_session"])
    token = auth.issue_session(user)
    session.clear()
    response = redirect(url_for("web.workspace"), code=303)
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
    if g.user:
        return redirect(url_for("web.workspace"))
    return render_template("home.html")


@web.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth.html", mode="register")
    rate_limit("registration-ip", request.remote_addr or "unknown", 20, 600)
    data = RegisterInput.model_validate(input_data())
    return set_session(auth.register(data))


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
        return render_template("auth.html", mode="login")
    rate_limit("login-ip", request.remote_addr or "unknown", 30, 600)
    data = LoginInput.model_validate(input_data())
    rate_limit("login-email", data.email, 10, 600)
    return set_session(auth.authenticate(data.email, data.password))


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
@login_required
def workspace():
    from app.models import (
        AIOperation,
        CommerceOrder,
        CreditAccount,
        CreditEntry,
        Diagnostic,
        JobTarget,
        Membership,
        Resume,
    )
    from app.services import commerce, credits
    from app.services.admin_config import runtime_commerce
    from app.services.career import owned, serialize_resume

    billing = request.args.get("view") == "billing"
    if billing:
        commerce.grant_due(g.user.id)
        db.session.commit()

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
    resume_id = request.args.get("resume_id", type=int)
    current_resume = serialize_resume(owned(Resume, g.user.id, resume_id)) if resume_id else None
    reports = db.session.execute(
        select(AIOperation, Diagnostic)
        .join(Diagnostic, AIOperation.diagnostic_id == Diagnostic.id)
        .where(
            AIOperation.user_id == g.user.id,
            AIOperation.kind == "report",
            AIOperation.state == "succeeded",
        )
        .order_by(AIOperation.id.desc())
        .limit(100)
    ).all()
    balance = db.session.get(CreditAccount, g.user.id)
    entries = db.session.scalars(
        select(CreditEntry)
        .where(CreditEntry.user_id == g.user.id)
        .order_by(CreditEntry.id.desc())
        .limit(100)
    ).all()
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
    offers, _ = runtime_commerce() if billing and commerce.mock_enabled() else (None, None)
    category_balances = credits.category_balances(g.user.id) if billing else {}
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
        current_resume=current_resume,
        reports=reports,
        balance=balance,
        entries=entries,
        membership=membership,
        orders=orders,
        offers=offers,
        mock_payment_enabled=commerce.mock_enabled(),
        category_balances=category_balances,
        new_request_key=uuid4,
        now=utcnow(),
    )


@web.post("/settings/theme")
@login_required
def theme():
    data = ThemeInput.model_validate(input_data())
    g.user.theme = data.theme
    db.session.commit()
    return {"theme": data.theme}


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
