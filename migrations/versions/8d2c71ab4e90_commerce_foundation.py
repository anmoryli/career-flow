"""Order snapshots, membership cycles and typed credit entries.

Revision ID: 8d2c71ab4e90
Revises: 3e019acf2e31
"""

import sqlalchemy as sa
from alembic import op

revision = "8d2c71ab4e90"
down_revision = "3e019acf2e31"
branch_labels = None
depends_on = None

OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade():
    op.create_table(
        "commerce_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("plan_code", sa.String(32), nullable=False),
        sa.Column("price_yuan", sa.Numeric(10, 2), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("config_revision_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "price_yuan >= 0 AND credits > 0", name="ck_commerce_orders_commerce_value_positive"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_commerce_orders_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["config_revision_id"],
            ["config_revisions.id"],
            name="fk_commerce_orders_config_revision_id_config_revisions",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("user_id", "request_key", name="uq_commerce_orders_user_id"),
        **OPTIONS,
    )
    op.create_index("ix_commerce_orders_user_id", "commerce_orders", ["user_id"])
    op.create_table(
        "memberships",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("next_grant_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"
        ),
        **OPTIONS,
    )
    op.create_table(
        "membership_cycles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["memberships.user_id"],
            name="fk_membership_cycles_user_id_memberships",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["commerce_orders.id"],
            name="fk_membership_cycles_order_id_commerce_orders",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "starts_at", name="uq_membership_cycles_user_id"),
        **OPTIONS,
    )
    # Existing balances and their historic entries belong to the experience pool.
    op.add_column(
        "credit_entries",
        sa.Column("category", sa.String(16), server_default="experience", nullable=False),
    )
    op.add_column("credit_entries", sa.Column("source_order_id", sa.Integer(), nullable=True))
    op.add_column("credit_entries", sa.Column("source_cycle_id", sa.Integer(), nullable=True))
    op.drop_constraint("uq_credit_entries_operation_id", "credit_entries", type_="unique")
    op.create_unique_constraint(
        "uq_credit_operation_kind_category",
        "credit_entries",
        ["operation_id", "kind", "category"],
    )
    op.create_unique_constraint(
        "uq_credit_entries_source_order_id", "credit_entries", ["source_order_id"]
    )
    op.create_unique_constraint(
        "uq_credit_entries_source_cycle_id", "credit_entries", ["source_cycle_id"]
    )
    op.create_foreign_key(
        "fk_credit_entries_source_order_id_commerce_orders",
        "credit_entries",
        "commerce_orders",
        ["source_order_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_credit_entries_source_cycle_id_membership_cycles",
        "credit_entries",
        "membership_cycles",
        ["source_cycle_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    # The new ledger and order records cannot be represented by the old schema.
    connection = op.get_bind()
    for table in ("commerce_orders", "membership_cycles", "memberships"):
        if connection.scalar(sa.text(f"SELECT COUNT(*) FROM {table}")):
            raise RuntimeError("Back up and explicitly reconcile commerce data before downgrading")
    if connection.scalar(
        sa.text("SELECT COUNT(*) FROM credit_entries WHERE category != 'experience'")
    ):
        raise RuntimeError("Typed credit entries cannot be downgraded without reconciliation")
    op.drop_constraint(
        "fk_credit_entries_source_cycle_id_membership_cycles", "credit_entries", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_credit_entries_source_order_id_commerce_orders", "credit_entries", type_="foreignkey"
    )
    op.drop_constraint("uq_credit_entries_source_cycle_id", "credit_entries", type_="unique")
    op.drop_constraint("uq_credit_entries_source_order_id", "credit_entries", type_="unique")
    op.drop_constraint("uq_credit_operation_kind_category", "credit_entries", type_="unique")
    op.create_unique_constraint(
        "uq_credit_entries_operation_id", "credit_entries", ["operation_id", "kind"]
    )
    op.drop_column("credit_entries", "source_cycle_id")
    op.drop_column("credit_entries", "source_order_id")
    op.drop_column("credit_entries", "category")
    op.drop_table("membership_cycles")
    op.drop_table("memberships")
    op.drop_index("ix_commerce_orders_user_id", table_name="commerce_orders")
    op.drop_table("commerce_orders")
