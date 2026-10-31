"""Product evidence, private export grants and revocable public snapshots."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models import TABLE_OPTIONS, utcnow


class ProductEvent(db.Model):
    __tablename__ = "product_events"
    __table_args__ = (UniqueConstraint("user_id", "event_key"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40), index=True)
    event_key: Mapped[str] = mapped_column(String(120))
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class ResumeExportGrant(db.Model):
    __tablename__ = "resume_export_grants"
    __table_args__ = TABLE_OPTIONS
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class ReportShare(db.Model):
    __tablename__ = "report_shares"
    __table_args__ = (UniqueConstraint("user_id", "request_key"), TABLE_OPTIONS)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_operations.id", ondelete="CASCADE"), index=True
    )
    request_key: Mapped[str] = mapped_column(String(36))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class ReferralCode(db.Model):
    __tablename__ = "referral_codes"
    __table_args__ = TABLE_OPTIONS
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class ReferralAttribution(db.Model):
    __tablename__ = "referral_attributions"
    __table_args__ = TABLE_OPTIONS
    new_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class ModelCallUsage(db.Model):
    __tablename__ = "model_call_usage"
    __table_args__ = (UniqueConstraint("operation_id", "attempt"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_operations.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int]
    model_id: Mapped[str] = mapped_column(String(160))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    total_tokens: Mapped[int | None]
    estimated_cost_cny: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    outcome: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
