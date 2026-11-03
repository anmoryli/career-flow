"""add ai_operations.note for the streamed analysis recap

Revision ID: a1b2c3d4e5f7
Revises: f1c2d3e4a5b6
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f1c2d3e4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    # MySQL rejects a DEFAULT on TEXT columns, so add it nullable, backfill the
    # existing rows, then tighten it.
    op.add_column("ai_operations", sa.Column("note", sa.Text(), nullable=True))
    op.execute("UPDATE ai_operations SET note = '' WHERE note IS NULL")
    op.alter_column(
        "ai_operations", "note", existing_type=sa.Text(), nullable=False
    )


def downgrade():
    op.drop_column("ai_operations", "note")
