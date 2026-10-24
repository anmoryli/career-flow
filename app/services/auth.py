import hashlib
import hmac
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from flask import current_app
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import (
    AdminAudit,
    AIOperation,
    AuthIdentity,
    ConfigRevision,
    CreditAccount,
    EmailVerificationCode,
    JobTarget,
    PasswordResetCode,
    User,
    UserSession,
    utcnow,
)
from app.schemas import AccountDeleteInput, ChangePasswordInput, PasswordResetInput, RegisterInput
from app.services.errors import BusinessError

DUMMY_HASH = generate_password_hash("dummy-not-a-real-user-password")


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def digest_code(email: str, code: str) -> str:
    return hmac.new(
        current_app.config["SESSION_ENCRYPTION_KEY"].encode(),
        f"registration:{email}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def digest_reset_code(email: str, code: str) -> str:
    return hmac.new(
        current_app.config["SESSION_ENCRYPTION_KEY"].encode(),
        f"password-reset:{email}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _deliver_code(mail, email, subject, body):
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = mail["sender"]
    message["To"] = email
    message.set_content(body)
    smtp_class = smtplib.SMTP_SSL if mail["use_ssl"] else smtplib.SMTP
    with smtp_class(mail["host"], mail["port"], timeout=8) as smtp:
        if mail["use_tls"]:
            import ssl

            smtp.starttls(context=ssl.create_default_context())
        if mail["username"]:
            smtp.login(mail["username"], mail["secret"])
        smtp.send_message(message)


def send_registration_code(email: str) -> None:
    from app.services.admin_config import runtime_mail

    mail = runtime_mail()
    if not mail["enabled"]:
        raise BusinessError("邮件服务暂不可用，请稍后重试。", 503)
    # Account discovery is not exposed by the HTTP response.
    if db.session.scalar(select(User.id).where(User.email == email)):
        return
    code = f"{secrets.randbelow(1000000):06d}"
    record = db.session.scalar(
        select(EmailVerificationCode).where(EmailVerificationCode.email == email).with_for_update()
    )
    if record is None:
        record = EmailVerificationCode(email=email)
        db.session.add(record)
    record.code_hash = digest_code(email, code)
    record.attempts = 0
    record.expires_at = utcnow() + timedelta(minutes=10)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise BusinessError("请求正在处理中，请稍后重试。", 409) from None
    try:
        _deliver_code(
            mail,
            email,
            "职序 CareerFlow 注册验证码",
            f"您的注册验证码为 {code}，10 分钟内有效。请勿向他人透露。",
        )
    except (OSError, smtplib.SMTPException):
        # Invalidate only this generation, preserving a newer concurrent send.
        db.session.execute(
            delete(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.code_hash == digest_code(email, code),
            )
        )
        db.session.commit()
        raise BusinessError("邮件发送失败，请稍后重新获取验证码。", 503) from None


def send_password_reset_code(email: str) -> None:
    from app.services.admin_config import runtime_mail

    mail = runtime_mail()
    if not mail["enabled"]:
        raise BusinessError("邮件服务暂不可用，请稍后重试。", 503)
    # Missing accounts get the same HTTP response without sending mail.
    if db.session.scalar(select(User.id).where(User.email == email)) is None:
        return
    code = f"{secrets.randbelow(1000000):06d}"
    record = db.session.scalar(
        select(PasswordResetCode).where(PasswordResetCode.email == email).with_for_update()
    )
    if record is None:
        record = PasswordResetCode(email=email)
        db.session.add(record)
    record.code_hash = digest_reset_code(email, code)
    record.attempts = 0
    record.expires_at = utcnow() + timedelta(minutes=10)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise BusinessError("请求正在处理中，请稍后重试。", 409) from None
    try:
        _deliver_code(
            mail,
            email,
            "职序 CareerFlow 重置密码验证码",
            f"您的密码重置验证码为 {code}，10 分钟内有效。若非本人操作，请忽略此邮件。",
        )
    except (OSError, smtplib.SMTPException):
        db.session.execute(
            delete(PasswordResetCode).where(
                PasswordResetCode.email == email,
                PasswordResetCode.code_hash == digest_reset_code(email, code),
            )
        )
        db.session.commit()
        raise BusinessError("邮件发送失败，请稍后重新获取验证码。", 503) from None


def reset_password(data: PasswordResetInput) -> None:
    record = db.session.scalar(
        select(PasswordResetCode).where(PasswordResetCode.email == data.email).with_for_update()
    )
    if record is None or record.expires_at <= utcnow() or record.attempts >= 5:
        raise BusinessError("验证码已失效，请重新获取。", 400)
    if not hmac.compare_digest(record.code_hash, digest_reset_code(data.email, data.code)):
        record.attempts += 1
        db.session.commit()
        raise BusinessError("验证码不正确。", 400)
    user = db.session.scalar(select(User).where(User.email == data.email).with_for_update())
    identity = (
        db.session.scalar(
            select(AuthIdentity).where(AuthIdentity.user_id == user.id).with_for_update()
        )
        if user
        else None
    )
    if identity is None:
        raise BusinessError("验证码已失效，请重新获取。", 400)
    identity.password_hash = generate_password_hash(data.new_password)
    db.session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.session.delete(record)
    db.session.commit()


def register(data: RegisterInput) -> User:
    record = db.session.scalar(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.email == data.email,
        )
        .with_for_update()
    )
    if record is None or record.expires_at <= utcnow() or record.attempts >= 5:
        db.session.rollback()
        raise BusinessError("验证码已失效，请重新获取。")
    if not hmac.compare_digest(record.code_hash, digest_code(data.email, data.code)):
        record.attempts += 1
        db.session.commit()
        raise BusinessError("验证码不正确。")
    user = User(email=data.email, display_name=data.display_name.strip())
    db.session.add(user)
    try:
        db.session.flush()
        db.session.add(
            AuthIdentity(
                user_id=user.id,
                password_hash=generate_password_hash(data.password),
            )
        )
        db.session.delete(record)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise BusinessError("注册未完成，请检查邮箱或直接登录。", 409) from None
    return user


def authenticate(email: str, password: str) -> User:
    user = db.session.scalar(select(User).where(User.email == email))
    identity = (
        db.session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.user_id == user.id,
            )
        )
        if user
        else None
    )
    valid = check_password_hash(identity.password_hash if identity else DUMMY_HASH, password)
    if not valid or not user:
        raise BusinessError("邮箱或密码不匹配。如果是首次使用，请先创建账号。", 401)
    return user


def issue_session(user: User) -> str:
    token = secrets.token_urlsafe(48)
    db.session.add(
        UserSession(
            user_id=user.id,
            token_hash=digest_token(token),
            expires_at=utcnow() + timedelta(days=30),
        )
    )
    db.session.commit()
    return token


def resolve_session(token: str) -> User | None:
    if not token or len(token) > 128:
        return None
    return db.session.scalar(
        select(User)
        .join(UserSession)
        .where(
            UserSession.token_hash == digest_token(token),
            UserSession.expires_at > utcnow(),
        )
    )


def revoke_session(token: str) -> None:
    db.session.execute(delete(UserSession).where(UserSession.token_hash == digest_token(token)))
    db.session.commit()


def revoke_all_sessions(user_id: int) -> None:
    db.session.execute(delete(UserSession).where(UserSession.user_id == user_id))
    db.session.commit()


def change_password(user_id: int, data: ChangePasswordInput) -> None:
    identity = db.session.scalar(
        select(AuthIdentity).where(AuthIdentity.user_id == user_id).with_for_update()
    )
    if identity is None or not check_password_hash(identity.password_hash, data.current_password):
        raise BusinessError("当前密码不正确。", 401)
    if check_password_hash(identity.password_hash, data.new_password):
        raise BusinessError("新密码不能与当前密码相同。", 422)
    identity.password_hash = generate_password_hash(data.new_password)
    db.session.execute(delete(UserSession).where(UserSession.user_id == user_id))
    db.session.commit()


def delete_account(user_id: int, data: AccountDeleteInput) -> None:
    """Permanently remove the signed-in account after password re-authentication.

    Business rows cascade from ``users``; in-flight AI work and frozen credits are
    refused instead of being silently dropped, and administrator accounts keep
    their audit trail and cannot self-delete.
    """
    user = db.session.scalar(select(User).where(User.id == user_id).with_for_update())
    identity = (
        db.session.scalar(
            select(AuthIdentity).where(AuthIdentity.user_id == user_id).with_for_update()
        )
        if user
        else None
    )
    if (
        user is None
        or identity is None
        or not check_password_hash(identity.password_hash, data.password)
    ):
        raise BusinessError("当前密码不正确。", 401)
    is_audited = db.session.scalar(
        select(AdminAudit.id).where(AdminAudit.actor_id == user_id).limit(1)
    ) or db.session.scalar(
        select(ConfigRevision.id).where(ConfigRevision.author_id == user_id).limit(1)
    )
    if user.is_admin or is_audited:
        raise BusinessError("管理员账户保留审计记录，不能自助注销。", 403)
    if db.session.scalar(
        select(AIOperation.id)
        .where(
            AIOperation.user_id == user_id,
            AIOperation.state.in_(("quoted", "queued", "running")),
        )
        .limit(1)
    ):
        raise BusinessError("还有进行中的诊断任务，请先取消或等待完成后再注销。", 409)
    account = db.session.get(CreditAccount, user_id)
    if account is not None and account.frozen:
        raise BusinessError("还有未结算的积分，请稍后再注销。", 409)
    db.session.execute(delete(JobTarget).where(JobTarget.user_id == user_id))
    db.session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.email == user.email)
    )
    db.session.execute(delete(PasswordResetCode).where(PasswordResetCode.email == user.email))
    db.session.delete(user)
    db.session.commit()
