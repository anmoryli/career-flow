"""Product events, export grants, revocable shares, referrals and model usage.
Revision ID: e8a431c02d9f
Revises: d71f4bce92aa
"""

import sqlalchemy as sa
from alembic import op

revision = "e8a431c02d9f"
down_revision = "d71f4bce92aa"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_events",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("name", sa.String(40), nullable=False, primary_key=False),
        sa.Column("event_key", sa.String(120), nullable=False, primary_key=False),
        sa.Column("properties", sa.JSON(), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint("user_id", "event_key"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_product_events_user_id", "product_events", ["user_id"])
    op.create_index("ix_product_events_name", "product_events", ["name"])
    op.create_index("ix_product_events_created_at", "product_events", ["created_at"])
    op.create_table(
        "resume_export_grants",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("resume_versions.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, primary_key=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_resume_export_grants_created_at", "resume_export_grants", ["created_at"])
    op.create_table(
        "report_shares",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("ai_operations.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("request_key", sa.String(36), nullable=False, primary_key=False),
        sa.Column("token_hash", sa.String(64), nullable=False, primary_key=False),
        sa.Column("snapshot", sa.JSON(), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, primary_key=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False, primary_key=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True, primary_key=False),
        sa.UniqueConstraint("user_id", "request_key"),
        sa.UniqueConstraint("token_hash"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_report_shares_user_id", "report_shares", ["user_id"])
    op.create_index("ix_report_shares_operation_id", "report_shares", ["operation_id"])
    op.create_index("ix_report_shares_created_at", "report_shares", ["created_at"])
    op.create_table(
        "referral_codes",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("code", sa.String(32), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint("code"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_referral_codes_created_at", "referral_codes", ["created_at"])
    op.create_table(
        "referral_attributions",
        sa.Column(
            "new_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "inviter_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, primary_key=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_referral_attributions_inviter_id", "referral_attributions", ["inviter_id"])
    op.create_index("ix_referral_attributions_created_at", "referral_attributions", ["created_at"])
    op.create_table(
        "model_call_usage",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("ai_operations.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("model_id", sa.String(160), nullable=False, primary_key=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("output_tokens", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("total_tokens", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("estimated_cost_cny", sa.Numeric(16, 6), nullable=True, primary_key=False),
        sa.Column("outcome", sa.String(24), nullable=False, primary_key=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint("operation_id", "attempt"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_model_call_usage_user_id", "model_call_usage", ["user_id"])
    op.create_index("ix_model_call_usage_operation_id", "model_call_usage", ["operation_id"])
    op.create_index("ix_model_call_usage_created_at", "model_call_usage", ["created_at"])


def downgrade():
    op.drop_table("model_call_usage")
    op.drop_table("referral_attributions")
    op.drop_table("referral_codes")
    op.drop_table("report_shares")
    op.drop_table("resume_export_grants")
    op.drop_table("product_events")
