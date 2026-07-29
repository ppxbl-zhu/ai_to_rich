"""Create genetic experiment lineage and promotion audit tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0004"
down_revision: str | None = "20260729_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evolution_experiments",
        sa.Column("experiment_id", sa.String(80), primary_key=True),
        sa.Column(
            "parent_experiment_id",
            sa.String(80),
            sa.ForeignKey("evolution_experiments.experiment_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_name", sa.String(80), nullable=False),
        sa.Column("strategy_version", sa.String(80), nullable=False),
        sa.Column("git_commit", sa.String(64), nullable=False),
        sa.Column("dataset_version", sa.String(80), nullable=False),
        sa.Column("universe_version", sa.String(80), nullable=False),
        sa.Column("train_period_json", sa.Text(), nullable=False),
        sa.Column("validation_period_json", sa.Text(), nullable=False),
        sa.Column("test_period_json", sa.Text(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("genome_json", sa.Text(), nullable=False),
        sa.Column("bounds_json", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("fitness", sa.Numeric(24, 10), nullable=False),
        sa.Column("llm_hypothesis_id", sa.String(80), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )
    op.create_table(
        "experiment_promotions",
        sa.Column("promotion_id", sa.String(80), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(80),
            sa.ForeignKey("evolution_experiments.experiment_id"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.String(160), nullable=True),
        sa.Column("approval_record", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("experiment_promotions")
    op.drop_table("evolution_experiments")
