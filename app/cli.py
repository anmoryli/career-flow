import secrets
import time
from pathlib import Path

import click
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app.services.infrastructure import readiness


def register_commands(app):
    @app.cli.command("bootstrap-admin")
    @click.argument("email")
    @click.option("--display-name", default="管理员", show_default=True)
    def bootstrap_admin(email, display_name):
        """Create the first administrator; save a one-time password in ignored instance/."""
        from app.extensions import db
        from app.models import AdminAudit, AuthIdentity, User
        from app.schemas import EmailInput

        normalized = EmailInput.model_validate({"email": email}).email
        if db.session.scalar(select(User.id).where(User.email == normalized)):
            raise click.ClickException("Account already exists; no account was changed")
        if db.session.scalar(select(User.id).where(User.is_admin.is_(True))):
            raise click.ClickException("Administrator already exists; bootstrap is disabled")
        password = secrets.token_urlsafe(24)
        path = Path(app.instance_path) / "admin-first-login.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise click.ClickException("One-time credential file already exists; move it first")
        created_file = False
        try:
            with path.open("x", encoding="utf-8") as credential_file:
                created_file = True
                credential_file.write(f"Email: {normalized}\nTemporary password: {password}\n")
            path.chmod(0o600)
            user = User(email=normalized, display_name=display_name, is_admin=True)
            db.session.add(user)
            db.session.flush()
            db.session.add(
                AuthIdentity(user_id=user.id, password_hash=generate_password_hash(password))
            )
            db.session.add(
                AdminAudit(
                    actor_id=user.id,
                    action="bootstrap_admin",
                    target=f"user:{user.id}",
                    before=None,
                    after={"created": True},
                    request_id="cli",
                )
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            if created_file:
                path.unlink(missing_ok=True)
            raise
        click.echo(f"Administrator created. One-time credentials: {path}")

    @app.cli.command("grant-development-credits")
    @click.argument("user_id", type=int)
    @click.argument("amount", type=click.IntRange(1, 1000000))
    def grant_development_credits(user_id, amount):
        """Explicit local development grant; never available in production."""
        from app.extensions import db
        from app.models import CreditEntry, User
        from app.services.diagnosis import account, owner_lock

        if app.config["APP_ENV"] == "production":
            raise click.ClickException("Development credits are disabled in production")
        if db.session.get(User, user_id) is None:
            raise click.ClickException("User not found")
        owner_lock(user_id)
        account(user_id).available += amount
        db.session.add(
            CreditEntry(user_id=user_id, kind="grant", available_delta=amount, frozen_delta=0)
        )
        db.session.commit()
        click.echo("Development grant recorded in credit ledger")

    @app.cli.command("recover-stale-tasks")
    def recover_stale_tasks_command():
        """Release timed-out reservations after worker interruption (five minutes)."""
        from app.services.diagnosis import recover_stale_tasks

        click.echo(f"Recovered tasks: {recover_stale_tasks()}")

    @app.cli.command("check-services")
    @click.option("--wait", default=0, type=click.IntRange(0, 180))
    def check_services(wait):
        """Check MySQL 8.4, current Alembic revision and Redis without exposing credentials."""
        deadline = time.monotonic() + wait
        while True:
            checks = readiness()
            if all(checks.values()) or time.monotonic() >= deadline:
                break
            time.sleep(2)
        for name, ok in checks.items():
            click.echo(f"{name}: {'ok' if ok else 'unavailable'}")
        if not all(checks.values()):
            raise click.ClickException("Infrastructure is not ready")
