from datetime import datetime

from sqlalchemy import JSON, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models import TABLE_OPTIONS, utcnow


class ResumeImport(db.Model):
    __tablename__ = "resume_imports"
    __table_args__ = (UniqueConstraint("user_id", "request_key"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(36))
    digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24), default="queued")
    content: Mapped[bytes | None] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql"))
    text: Mapped[str] = mapped_column(Text, default="")
    document: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
