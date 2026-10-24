from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models import TABLE_OPTIONS, utcnow


class ConfigRevision(db.Model):
    __tablename__ = "config_revisions"
    __table_args__ = (UniqueConstraint("category", "version"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int]
    label: Mapped[str] = mapped_column(String(100))
    settings: Mapped[dict] = mapped_column(JSON)
    encrypted_secret: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(16), default="draft")
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    published_at: Mapped[datetime | None]


class ActiveConfig(db.Model):
    __tablename__ = "active_configs"
    __table_args__ = TABLE_OPTIONS
    category: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("config_revisions.id", ondelete="RESTRICT"), unique=True
    )
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AdminAudit(db.Model):
    __tablename__ = "admin_audit_entries"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    target: Mapped[str] = mapped_column(String(100))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    request_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
