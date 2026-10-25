from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models import TABLE_OPTIONS, utcnow


class CreditAccount(db.Model):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint("available >= 0 AND frozen >= 0", name="credit_nonnegative"),
        TABLE_OPTIONS,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    available: Mapped[int] = mapped_column(default=0)
    frozen: Mapped[int] = mapped_column(default=0)


class Diagnostic(db.Model):
    __tablename__ = "diagnostics"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job_targets.id", ondelete="CASCADE"), unique=True
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True
    )
    rounds: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(String(24), default="active")
    question: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=0)


class DiagnosticAnswer(db.Model):
    __tablename__ = "diagnostic_answers"
    __table_args__ = (
        UniqueConstraint("diagnostic_id", "round"),
        UniqueConstraint("diagnostic_id", "request_key", name="uq_answer_request"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    diagnostic_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostics.id", ondelete="CASCADE"), index=True
    )
    round: Mapped[int]
    request_key: Mapped[str] = mapped_column(String(36))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    skipped: Mapped[bool]


class AIOperation(db.Model):
    __tablename__ = "ai_operations"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key"),
        CheckConstraint(
            "(diagnostic_id IS NULL) <> (resume_id IS NULL)", name="ai_operation_one_owner"
        ),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    diagnostic_id: Mapped[int | None] = mapped_column(
        ForeignKey("diagnostics.id", ondelete="CASCADE"), index=True
    )
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    request_key: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(24), default="quoted")
    diagnostic_revision: Mapped[int]
    ceiling: Mapped[int]
    charged: Mapped[int] = mapped_column(default=0)
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(String(200), default="")
    attempts: Mapped[int] = mapped_column(default=0)
    tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    started_at: Mapped[datetime | None]


class CreditEntry(db.Model):
    __tablename__ = "credit_entries"
    __table_args__ = (
        UniqueConstraint(
            "operation_id", "kind", "category", name="uq_credit_operation_kind_category"
        ),
        UniqueConstraint("source_order_id", name="uq_credit_entries_source_order_id"),
        UniqueConstraint("source_cycle_id", name="uq_credit_entries_source_cycle_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_operations.id", ondelete="CASCADE"), index=True
    )
    source_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("commerce_orders.id", ondelete="CASCADE")
    )
    source_cycle_id: Mapped[int | None] = mapped_column(
        ForeignKey("membership_cycles.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(
        String(16), default="experience", server_default="experience"
    )
    available_delta: Mapped[int]
    frozen_delta: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
