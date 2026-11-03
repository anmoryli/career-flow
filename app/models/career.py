"""Relational ownership links plus the one current structured document per resume."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models import TABLE_OPTIONS, utcnow


class Resume(db.Model):
    """One current document per resume: saving overwrites, no version history."""

    __tablename__ = "resumes"
    __table_args__ = (UniqueConstraint("user_id", "request_key"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(120))
    template: Mapped[str] = mapped_column(String(16), default="classic")
    document: Mapped[dict] = mapped_column(JSON, default=dict)
    # Monotonic counter for optimistic concurrency and analysis provenance;
    # it is not a version history.
    revision: Mapped[int] = mapped_column(default=0)
    last_save_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class JobTarget(db.Model):
    __tablename__ = "job_targets"
    __table_args__ = (UniqueConstraint("user_id", "request_key"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(36))
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="RESTRICT"), index=True
    )
    resume_revision: Mapped[int] = mapped_column(default=0)
    title: Mapped[str] = mapped_column(String(160))
    company: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    is_saved: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
