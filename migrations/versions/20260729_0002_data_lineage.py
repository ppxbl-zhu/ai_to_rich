"""Create point-in-time dataset lineage tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0002"
down_revision: str | None = "20260729_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("version", sa.String(80), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "data_records",
        sa.Column(
            "dataset_version",
            sa.String(80),
            sa.ForeignKey("datasets.version"),
            primary_key=True,
        ),
        sa.Column("record_id", sa.String(200), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("quality", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "provider_probes",
        sa.Column("probe_id", sa.String(32), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_probes")
    op.drop_table("data_records")
    op.drop_table("datasets")
