"""Create paper operations, reconciliation, and simulation audit tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0005"
down_revision: str | None = "20260729_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operations_snapshots",
        sa.Column("snapshot_id", sa.String(80), primary_key=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "scheduled_job_runs",
        sa.Column("run_id", sa.String(80), primary_key=True),
        sa.Column("job_name", sa.String(120), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "reconciliation_runs",
        sa.Column("run_id", sa.String(80), primary_key=True),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("differences_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "operations_incidents",
        sa.Column("incident_id", sa.String(80), primary_key=True),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
    )
    op.create_table(
        "simulation_days",
        sa.Column("trading_date", sa.Date(), primary_key=True),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("reconciled", sa.Boolean(), nullable=False),
        sa.Column("critical_incident", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("simulation_days")
    op.drop_table("operations_incidents")
    op.drop_table("reconciliation_runs")
    op.drop_table("scheduled_job_runs")
    op.drop_table("operations_snapshots")
