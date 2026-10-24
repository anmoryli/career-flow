"""Persist validated structured interactions and user submissions.

Revision ID: 9c75e89d41a0
Revises: a8f6d92b37e1
"""

import sqlalchemy as sa
from alembic import op

revision = "9c75e89d41a0"
down_revision = "a8f6d92b37e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "structured_interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("submission", sa.JSON(), nullable=True),
        sa.Column("request_key", sa.String(36), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operation_id"], ["ai_operations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("operation_id", name="uq_interaction_operation"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_structured_interactions_conversation_id", "structured_interactions", ["conversation_id"]
    )


def downgrade():
    op.drop_table("structured_interactions")
