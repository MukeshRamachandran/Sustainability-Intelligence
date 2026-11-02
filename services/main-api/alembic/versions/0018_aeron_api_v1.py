"""Record Aeron REST API v1 provenance on environment readings.

Revision ID: 0018_aeron_api_v1
Revises: 0017_public_certificate_registry

Additive only: three nullable columns on ``environment.readings``. Existing
rows (normalizer v1, cookie-authenticated route) keep their values and get
NULL in the new columns. Nothing is dropped, rewritten or backfilled.

- ``fetched_at``: when the worker received the response (UTC), distinct from
  ``observed_at`` (sensor time) and ``ingested_at`` (storage time).
- ``source_epoch_ms``: the ``reading.epoch_ms`` Aeron sent alongside the timestamp.
- ``unmapped_values``: parameter IDs not in the K-COSMOS map, with their raw values.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018_aeron_api_v1"
down_revision = "0017_public_certificate_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("readings", sa.Column("fetched_at", sa.DateTime(timezone=True)), schema="environment")
    op.add_column("readings", sa.Column("source_epoch_ms", sa.BigInteger()), schema="environment")
    op.add_column("readings", sa.Column("unmapped_values", postgresql.JSONB()), schema="environment")


def downgrade() -> None:
    op.drop_column("readings", "unmapped_values", schema="environment")
    op.drop_column("readings", "source_epoch_ms", schema="environment")
    op.drop_column("readings", "fetched_at", schema="environment")
