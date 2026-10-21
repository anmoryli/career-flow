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
from app.models import AuthIdentity, EmailVerificationCode, User, UserSession, utcnow
from app.schemas import RegisterInput
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


def send_registration_code(email: str) -> None:
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
    message = EmailMessage()
    message["Subject"] = "职序 CareerFlow 注册验证码"
    message["From"] = current_app.config["MAIL_DEFAULT_SENDER"]
    message["To"] = email
    message.set_content(f"您的注册验证码为 {code}，10 分钟内有效。请勿向他人透露。")
    try:
        with smtplib.SMTP(
            current_app.config["MAIL_SERVER"],
            current_app.config["MAIL_PORT"],
            timeout=8,
        ) as smtp:
            if current_app.config["MAIL_USE_TLS"]:
                import ssl

                smtp.starttls(context=ssl.create_default_context())
            if current_app.config["MAIL_USERNAME"]:
                smtp.login(current_app.config["MAIL_USERNAME"], current_app.config["MAIL_PASSWORD"])
            smtp.send_message(message)
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
        raise BusinessError("邮箱或密码不正确。", 401)
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
