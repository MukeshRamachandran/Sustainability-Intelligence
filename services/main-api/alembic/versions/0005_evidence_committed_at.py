"""Distinguish temporary working evidence from committed evidence.

Revision ID: 0005_evidence_committed_at
Revises: 0004_submission_evidence
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_evidence_committed_at"
down_revision: str | None = "0004_submission_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "submission_evidence",
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        schema="sustainability",
    )
    # Existing evidence predates the temporary/committed distinction. Preserve it
    # as institutional history rather than risking destructive reclassification.
    op.execute(
        "UPDATE sustainability.submission_evidence "
        "SET committed_at = COALESCE(uploaded_at, now()) "
        "WHERE committed_at IS NULL"
    )
    op.create_index(
        "ix_submission_evidence_submission_committed",
        "submission_evidence",
        ["submission_id", "committed_at"],
        schema="sustainability",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_submission_evidence_submission_committed",
        table_name="submission_evidence",
        schema="sustainability",
    )
    op.drop_column("submission_evidence", "committed_at", schema="sustainability")
