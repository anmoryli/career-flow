"""One-time email codes for password recovery.

Revision ID: 3e019acf2e31
Revises: 9c75e89d41a0
"""

import sqlalchemy as sa
from alembic import op

revision = "3e019acf2e31"
down_revision = "9c75e89d41a0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "password_reset_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    op.drop_table("password_reset_codes")
