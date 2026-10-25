"""Persistent snapshots for mock checkout and manually renewed memberships."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models import TABLE_OPTIONS, utcnow


class CommerceOrder(db.Model):
    __tablename__ = "commerce_orders"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key"),
        CheckConstraint("price_yuan >= 0 AND credits > 0", name="commerce_value_positive"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(16))  # credits or membership
    plan_code: Mapped[str] = mapped_column(String(32))
    price_yuan: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    credits: Mapped[int]
    period_days: Mapped[int]  # zero for a one-time credit pack
    state: Mapped[str] = mapped_column(String(16), default="pending")
    config_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("config_revisions.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None]


class Membership(db.Model):
    __tablename__ = "memberships"
    __table_args__ = TABLE_OPTIONS
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    expires_at: Mapped[datetime]
    next_grant_at: Mapped[datetime]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class MembershipCycle(db.Model):
    __tablename__ = "membership_cycles"
    __table_args__ = (UniqueConstraint("user_id", "starts_at"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("memberships.user_id", ondelete="CASCADE"))
    order_id: Mapped[int] = mapped_column(ForeignKey("commerce_orders.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    credits: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
