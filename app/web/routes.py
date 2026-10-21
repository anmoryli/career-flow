from functools import wraps
from uuid import uuid4

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import delete, func, select

from app.extensions import db
from app.models import Conversation, ConversationMemory, ConversationMessage
from app.schemas import (
    ConversationInput,
    EmailInput,
    LoginInput,
    MemoryInput,
    MessageInput,
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
    return render_template("workspace.html", conversations=conversations, count=count)


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
    item = owned_conversation(g.user.id, conversation_id, lock=True)
    if request.form.get("confirm") != "delete":
        raise BusinessError("请确认永久删除此对话。")
    db.session.execute(delete(Conversation).where(Conversation.id == item.id))
    db.session.commit()
    flash("对话与关联消息、记忆已永久删除。", "success")
    return redirect(url_for("web.workspace"), code=303)
