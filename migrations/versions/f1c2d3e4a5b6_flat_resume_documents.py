"""flat resume documents

Drop resume version history: each resume keeps one current document that saving
overwrites. Latest version content is copied into ``resumes`` before the table
is removed.

Revision ID: f1c2d3e4a5b6
Revises: e8a431c02d9f
Create Date: 2026-11-03 16:05:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1c2d3e4a5b6"
down_revision = "e8a431c02d9f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "resumes",
        sa.Column("template", sa.String(length=16), nullable=False, server_default="classic"),
    )
    op.add_column("resumes", sa.Column("document", sa.JSON(), nullable=True))
    op.add_column(
        "resumes",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.add_column("resumes", sa.Column("last_save_key", sa.String(length=36), nullable=True))
    op.execute(
        """
        UPDATE resumes AS r
        JOIN resume_versions AS v
          ON v.resume_id = r.id AND v.revision = r.revision
        SET r.template = v.template,
            r.document = v.document,
            r.created_at = v.created_at
        """
    )
    op.execute("UPDATE resumes SET document = JSON_OBJECT() WHERE document IS NULL")
    op.alter_column("resumes", "document", existing_type=sa.JSON(), nullable=False)

    op.add_column("job_targets", sa.Column("resume_id", sa.Integer(), nullable=True))
    op.add_column(
        "job_targets",
        sa.Column("resume_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE job_targets AS j
        JOIN resume_versions AS v ON v.id = j.resume_version_id
        SET j.resume_id = v.resume_id,
            j.resume_revision = v.revision
        """
    )
    op.alter_column("job_targets", "resume_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint(
        "fk_job_targets_resume_version_id_resume_versions", "job_targets", type_="foreignkey"
    )
    op.drop_index("ix_job_targets_resume_version_id", table_name="job_targets")
    op.drop_column("job_targets", "resume_version_id")
    op.create_index("ix_job_targets_resume_id", "job_targets", ["resume_id"], unique=False)
    op.create_foreign_key(
        "fk_job_targets_resume_id_resumes",
        "job_targets",
        "resumes",
        ["resume_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column("resume_export_grants", sa.Column("resume_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE resume_export_grants AS g
        JOIN resume_versions AS v ON v.id = g.version_id
        SET g.resume_id = v.resume_id
        """
    )
    op.drop_constraint(
        "fk_resume_export_grants_version_id_resume_versions",
        "resume_export_grants",
        type_="foreignkey",
    )
    op.drop_column("resume_export_grants", "version_id")
    op.create_foreign_key(
        "fk_resume_export_grants_resume_id_resumes",
        "resume_export_grants",
        "resumes",
        ["resume_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_table("resume_versions")


def downgrade():
    op.create_table(
        "resume_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("template", sa.String(length=16), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["resume_id"],
            ["resumes.id"],
            name=op.f("fk_resume_versions_resume_id_resumes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resume_versions")),
        sa.UniqueConstraint("resume_id", "request_key", name="uq_resume_versions_request"),
        sa.UniqueConstraint("resume_id", "revision", name="uq_resume_versions_revision"),
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.execute(
        """
        INSERT INTO resume_versions
            (resume_id, revision, request_key, title, template, document, created_at)
        SELECT id, revision, COALESCE(last_save_key, request_key), title, template, document,
               created_at
        FROM resumes
        """
    )
    op.create_index(
        "ix_resume_versions_resume_id", "resume_versions", ["resume_id"], unique=False
    )

    op.add_column("resume_export_grants", sa.Column("version_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE resume_export_grants AS g
        JOIN resume_versions AS v
          ON v.resume_id = g.resume_id AND v.revision = (
              SELECT MAX(v2.revision) FROM resume_versions AS v2 WHERE v2.resume_id = g.resume_id
          )
        SET g.version_id = v.id
        """
    )
    op.drop_constraint(
        "fk_resume_export_grants_resume_id_resumes",
        "resume_export_grants",
        type_="foreignkey",
    )
    op.drop_column("resume_export_grants", "resume_id")
    op.create_foreign_key(
        "fk_resume_export_grants_version_id_resume_versions",
        "resume_export_grants",
        "resume_versions",
        ["version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("job_targets", sa.Column("resume_version_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE job_targets AS j
        JOIN resume_versions AS v
          ON v.resume_id = j.resume_id AND v.revision = j.resume_revision
        SET j.resume_version_id = v.id
        """
    )
    op.alter_column("job_targets", "resume_version_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("fk_job_targets_resume_id_resumes", "job_targets", type_="foreignkey")
    op.drop_index("ix_job_targets_resume_id", table_name="job_targets")
    op.drop_column("job_targets", "resume_id")
    op.drop_column("job_targets", "resume_revision")
    op.create_index(
        "ix_job_targets_resume_version_id", "job_targets", ["resume_version_id"], unique=False
    )
    op.create_foreign_key(
        "fk_job_targets_resume_version_id_resume_versions",
        "job_targets",
        "resume_versions",
        ["resume_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_column("resumes", "last_save_key")
    op.drop_column("resumes", "created_at")
    op.drop_column("resumes", "document")
    op.drop_column("resumes", "template")
