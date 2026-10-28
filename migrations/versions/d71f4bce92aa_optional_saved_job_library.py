"""Track which analyzed job descriptions belong in the reusable saved library.

Revision ID: d71f4bce92aa
Revises: b32f1d75a8c4
"""

import sqlalchemy as sa
from alembic import op

revision = "d71f4bce92aa"
down_revision = "b32f1d75a8c4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "job_targets",
        sa.Column("is_saved", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade():
    op.drop_column("job_targets", "is_saved")
