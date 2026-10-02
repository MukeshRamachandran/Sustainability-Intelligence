"""Public certificate registry

Project-owner decision (2026-10-02). Certificates are supporting public
documents (for example an e-waste disposal certificate). They are administered
by an Admin and shown publicly once published. They are NOT sustainability
metric inputs: ``quantity_value`` is document metadata only and is never read
by any calculation, resolver or release.

Schema (additive only; no existing table or row is touched):
  * ``publication.certificates`` - one row per document. The file itself lives
    in a dedicated certificate storage root, never in the database; the row
    keeps an opaque ``storage_key`` and the file's SHA-256.

``reporting_year`` is stored on its own and is not derived from
``certificate_date``: a certificate issued in January 2026 for waste received in
November 2025 belongs to reporting year 2025.

A document is DRAFT, then PUBLISHED, then (instead of being deleted) ARCHIVED.
``sha256`` is unique, so the same file cannot be registered twice.

The downgrade drops only this table. Stored files are left on disk.

Revision ID: 0017_public_certificate_registry
Revises: 0016_renewable_excludes_thermal
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017_public_certificate_registry"
down_revision = "0016_renewable_excludes_thermal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("certificate_type", sa.Text(), nullable=False),
        sa.Column("reporting_year", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("issuer", sa.Text()),
        sa.Column("registration_id", sa.Text()),
        sa.Column("authorization_no", sa.Text()),
        sa.Column("serial_no", sa.Text()),
        sa.Column("certificate_date", sa.Date()),
        sa.Column("received_date", sa.Date()),
        sa.Column("invoice_no", sa.Text()),
        sa.Column("manifest_doc_no", sa.Text()),
        sa.Column("quantity_value", sa.Numeric(14, 3)),
        sa.Column("quantity_unit", sa.Text()),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="DRAFT"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["created_by"], ["identity.users.id"], name="fk_certificates_created_by_users", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("storage_key", name="uq_certificates_storage_key"),
        sa.UniqueConstraint("sha256", name="uq_certificates_sha256"),
        sa.CheckConstraint("status in ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_certificates_status_allowed"),
        sa.CheckConstraint("domain ~ '^[a-z][a-z0-9_]{1,39}$'", name="ck_certificates_domain_format"),
        sa.CheckConstraint("reporting_year between 2000 and 2100", name="ck_certificates_reporting_year_range"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_certificates_title_required"),
        sa.CheckConstraint("length(trim(certificate_type)) > 0", name="ck_certificates_type_required"),
        sa.CheckConstraint("quantity_value is null or quantity_value >= 0", name="ck_certificates_quantity_non_negative"),
        sa.CheckConstraint("byte_size > 0", name="ck_certificates_byte_size_positive"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_certificates_sha256_format"),
        sa.CheckConstraint(
            "mime_type in ('image/jpeg', 'image/png', 'application/pdf')", name="ck_certificates_mime_allowed"
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' and published_at is null and archived_at is null)"
            " or (status = 'PUBLISHED' and published_at is not null and archived_at is null)"
            " or (status = 'ARCHIVED' and archived_at is not null)",
            name="ck_certificates_status_timestamps",
        ),
        schema="publication",
    )
    op.create_index(
        "ix_certificates_public_lookup",
        "certificates",
        ["domain", "reporting_year", "status"],
        schema="publication",
    )


def downgrade() -> None:
    op.drop_index("ix_certificates_public_lookup", table_name="certificates", schema="publication")
    op.drop_table("certificates", schema="publication")
