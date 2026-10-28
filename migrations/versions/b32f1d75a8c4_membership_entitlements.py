"""Replace credit packs with fixed monthly and quarterly membership access.

Revision ID: b32f1d75a8c4
Revises: e6a291a24b51
"""

import sqlalchemy as sa
from alembic import op

revision = "b32f1d75a8c4"
down_revision = "e6a291a24b51"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "plan_code" not in {column["name"] for column in inspector.get_columns("memberships")}:
        op.add_column(
            "memberships",
            sa.Column("plan_code", sa.String(length=24), server_default="legacy", nullable=False),
        )
    constraints = inspector.get_check_constraints("commerce_orders")
    positive = next(
        (
            constraint["name"]
            for constraint in constraints
            if "credits" in constraint.get("sqltext", "")
            and "> 0" in constraint.get("sqltext", "")
        ),
        None,
    )
    if positive:
        op.drop_constraint(op.f(positive), "commerce_orders", type_="check")
    if not any(
        "credits" in constraint.get("sqltext", "")
        and ">= 0" in constraint.get("sqltext", "")
        for constraint in constraints
    ):
        op.create_check_constraint(
            op.f("ck_commerce_orders_commerce_value_nonnegative"),
            "commerce_orders",
            "price_yuan >= 0 AND credits >= 0",
        )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM commerce_orders WHERE credits = 0")):
        raise RuntimeError("Membership orders use zero legacy credits and cannot be downgraded")
    constraints = sa.inspect(connection).get_check_constraints("commerce_orders")
    target = next(
        (
            constraint["name"]
            for constraint in constraints
            if "credits" in constraint.get("sqltext", "")
            and ">= 0" in constraint.get("sqltext", "")
        ),
        None,
    )
    if target:
        op.drop_constraint(op.f(target), "commerce_orders", type_="check")
    op.create_check_constraint(
        op.f("ck_commerce_orders_commerce_value_positive"),
        "commerce_orders",
        "price_yuan >= 0 AND credits > 0",
    )
    op.drop_column("memberships", "plan_code")
