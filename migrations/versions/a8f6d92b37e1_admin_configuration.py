"""Administrator role, versioned runtime configuration and audit.

Revision ID: a8f6d92b37e1
Revises: 05373fa1964b
"""

from alembic import op
import sqlalchemy as sa

revision = "a8f6d92b37e1"
down_revision = "05373fa1964b"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
    op.create_table(
        "config_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("category", "version"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_config_revisions_category", "config_revisions", ["category"])
    op.create_table(
        "active_configs",
        sa.Column("category", sa.String(40), primary_key=True),
        sa.Column("revision_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["config_revisions.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "admin_audit_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_admin_audit_entries_actor_id", "admin_audit_entries", ["actor_id"])
    op.create_index("ix_admin_audit_entries_created_at", "admin_audit_entries", ["created_at"])


def downgrade():
    op.drop_table("admin_audit_entries")
    op.drop_table("active_configs")
    op.drop_table("config_revisions")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_admin")
