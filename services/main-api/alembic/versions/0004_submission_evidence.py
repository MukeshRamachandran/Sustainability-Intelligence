"""Add private generic submission evidence metadata.

Revision ID: 0004_submission_evidence
Revises: 0003_outreach_impact
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_submission_evidence"
down_revision: str | None = "0003_outreach_impact"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "submission_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_code", sa.String(length=100), nullable=True),
        sa.Column("evidence_category", sa.String(length=100), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("mime_type", sa.String(length=40), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("file_size_bytes > 0", name="ck_submission_evidence_evidence_file_size_positive"),
        sa.CheckConstraint("revision_number > 0", name="ck_submission_evidence_evidence_revision_positive"),
        sa.ForeignKeyConstraint(
            ["metric_code"], ["sustainability.metric_definitions.code"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_evidence_id"], ["sustainability.submission_evidence.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["sustainability.submissions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["identity.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_submission_evidence_storage_key"),
        schema="sustainability",
    )
    op.create_index(
        "ix_submission_evidence_submission_uploaded",
        "submission_evidence",
        ["submission_id", "uploaded_at"],
        schema="sustainability",
    )
    op.create_index(
        "ix_submission_evidence_uploader",
        "submission_evidence",
        ["uploaded_by_user_id"],
        schema="sustainability",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_submission_evidence_uploader", table_name="submission_evidence", schema="sustainability"
    )
    op.drop_index(
        "ix_submission_evidence_submission_uploaded",
        table_name="submission_evidence",
        schema="sustainability",
    )
    op.drop_table("submission_evidence", schema="sustainability")
