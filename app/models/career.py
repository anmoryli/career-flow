"""Relational ownership/version links with immutable structured document snapshots."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models import TABLE_OPTIONS, utcnow


class Resume(db.Model):
    __tablename__ = "resumes"
    __table_args__ = (UniqueConstraint("user_id", "request_key"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(default=0)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ResumeVersion(db.Model):
    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("resume_id", "revision", name="uq_resume_versions_revision"),
        UniqueConstraint("resume_id", "request_key", name="uq_resume_versions_request"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int]
    request_key: Mapped[str] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(120))
    template: Mapped[str] = mapped_column(String(16))
    document: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class JobTarget(db.Model):
    __tablename__ = "job_targets"
    __table_args__ = (UniqueConstraint("user_id", "request_key"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(36))
    resume_version_id: Mapped[int] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    company: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    is_saved: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
