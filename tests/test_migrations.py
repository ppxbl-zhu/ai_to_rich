from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_latest_migration_creates_append_only_trading_ledger(tmp_path: Path) -> None:
    database = tmp_path / "quantagent.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")

    command.upgrade(config, "head")

    tables = set(
        inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_table_names()
    )
    assert {
        "alembic_version",
        "data_records",
        "datasets",
        "order_intents",
        "fills",
        "portfolio_snapshots",
        "provider_probes",
        "research_calls",
        "research_evidence",
    } <= tables
