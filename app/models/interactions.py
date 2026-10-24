from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models import TABLE_OPTIONS, utcnow


class StructuredInteraction(db.Model):
    __tablename__ = "structured_interactions"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_interaction_operation"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    operation_id: Mapped[int] = mapped_column(ForeignKey("ai_operations.id", ondelete="CASCADE"))
    definition: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="waiting_for_user")
    submission: Mapped[dict | None] = mapped_column(JSON)
    request_key: Mapped[str | None] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    submitted_at: Mapped[datetime | None]
