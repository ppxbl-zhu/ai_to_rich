"""Create the append-only paper-trading ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_intents",
        sa.Column("idempotency_key", sa.String(160), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("limit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "fills",
        sa.Column("fill_id", sa.String(32), primary_key=True),
        sa.Column(
            "idempotency_key",
            sa.String(160),
            sa.ForeignKey("order_intents.idempotency_key"),
            nullable=False,
            unique=True,
        ),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("fee", sa.Numeric(18, 2), nullable=False),
    )
    op.create_table(
        "portfolio_snapshots",
        sa.Column("snapshot_id", sa.String(32), primary_key=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("cash", sa.Numeric(18, 2), nullable=False),
        sa.Column("positions_json", sa.Text(), nullable=False),
        sa.Column("source_fill_id", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("portfolio_snapshots")
    op.drop_table("fills")
    op.drop_table("order_intents")
