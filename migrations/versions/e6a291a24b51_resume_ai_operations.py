"""Allow billed AI operations to belong to a resume.

Revision ID: e6a291a24b51
Revises: 8d2c71ab4e90
"""

import sqlalchemy as sa
from alembic import op

revision = "e6a291a24b51"
down_revision = "8d2c71ab4e90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_operations", sa.Column("resume_id", sa.Integer(), nullable=True))
    op.alter_column("ai_operations", "diagnostic_id", existing_type=sa.Integer(), nullable=True)
    op.create_index(op.f("ix_ai_operations_resume_id"), "ai_operations", ["resume_id"])
    op.create_foreign_key(
        op.f("fk_ai_operations_resume_id_resumes"),
        "ai_operations",
        "resumes",
        ["resume_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        op.f("ck_ai_operations_ai_operation_one_owner"),
        "ai_operations",
        "(diagnostic_id IS NULL) <> (resume_id IS NULL)",
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM ai_operations WHERE resume_id IS NOT NULL")):
        raise RuntimeError("Resume AI operations exist; archive them before downgrading")
    op.drop_constraint(
        op.f("ck_ai_operations_ai_operation_one_owner"), "ai_operations", type_="check"
    )
    op.drop_constraint(
        op.f("fk_ai_operations_resume_id_resumes"), "ai_operations", type_="foreignkey"
    )
    op.drop_index(op.f("ix_ai_operations_resume_id"), table_name="ai_operations")
    op.drop_column("ai_operations", "resume_id")
    op.alter_column("ai_operations", "diagnostic_id", existing_type=sa.Integer(), nullable=False)
