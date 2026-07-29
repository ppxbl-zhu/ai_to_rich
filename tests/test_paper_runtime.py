from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from quantagent.closing import ClosingCandidate
from quantagent.domain import Board, MarketQuote, SecurityStatus
from quantagent.paper_runtime import (
    JsonStateStore,
    PaperRuntime,
    PaperSession,
    RuntimeStatus,
)
from quantagent.swing import MarketRegime, SwingCandidate

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 14, 50, 10, tzinfo=CST)


def quote(symbol: str, price: str) -> MarketQuote:
    value = Decimal(price)
    return MarketQuote(
        symbol=symbol,
        name=f"Test {symbol}",
        board=Board.CHINEXT if symbol.startswith("3") else Board.MAIN,
        market_time=NOW,
        captured_at=NOW,
        price=value,
        previous_close=value - Decimal("0.20"),
        limit_up=value + Decimal("2"),
        limit_down=value - Decimal("2"),
        status=SecurityStatus.ACTIVE,
        source="offline-session",
    )


def session(*, captured_at: datetime = NOW) -> PaperSession:
    return PaperSession(
        session_id="session-20260729-1450",
        trading_date=date(2026, 7, 29),
        captured_at=captured_at,
        dataset_version="sha256:session-data",
        is_trading_day=True,
        quotes={
            "000001.SZ": quote("000001.SZ", "12"),
            "300001.SZ": quote("300001.SZ", "20"),
        },
        swing_candidates=(
            SwingCandidate(
                symbol="000001.SZ",
                price=Decimal("12"),
                ma20=Decimal("11.5"),
                ma60=Decimal("10.5"),
                weekly_ma10=Decimal("10.8"),
                relative_strength_60d=Decimal("0.12"),
                sector_relative_strength=Decimal("0.08"),
                roe=Decimal("0.14"),
                operating_cashflow_positive=True,
                debt_ratio=Decimal("0.45"),
                atr=Decimal("0.40"),
                market_regime=MarketRegime.RISK_ON,
            ),
        ),
        closing_candidates=(
            ClosingCandidate(
                symbol="300001.SZ",
                observed_at=NOW.time().replace(tzinfo=None),
                price=Decimal("20"),
                vwap=Decimal("19.6"),
                close_location=Decimal("0.90"),
                volume_ratio=Decimal("1.8"),
                turnover=Decimal("120000000"),
                stock_relative_strength=Decimal("0.08"),
                sector_relative_strength=Decimal("0.06"),
                sector_breadth=Decimal("0.70"),
                at_limit_up=False,
                fresh=True,
            ),
        ),
    )


def test_started_runtime_runs_full_paper_pipeline_once(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "runtime.json")
    runtime = PaperRuntime(store)

    assert runtime.run_once(session(), now=NOW).status is RuntimeStatus.STOPPED

    runtime.start(NOW)
    report = runtime.run_once(session(), now=NOW)
    state = store.load()

    assert report.status is RuntimeStatus.COMPLETED
    assert report.generated_plans == 2
    assert report.fills == 2
    assert state.cash == Decimal("86389.86")
    assert state.positions == {"000001.SZ": 800, "300001.SZ": 200}
    assert state.processed_session_ids == ("session-20260729-1450",)

    repeated = runtime.run_once(session(), now=NOW)
    assert repeated.status is RuntimeStatus.ALREADY_PROCESSED
    assert store.load() == state


def test_runtime_fails_closed_on_stale_data_without_mutating_portfolio(
    tmp_path: Path,
) -> None:
    store = JsonStateStore(tmp_path / "runtime.json")
    runtime = PaperRuntime(store)
    runtime.start(NOW)
    before = store.load()

    report = runtime.run_once(session(captured_at=NOW - timedelta(minutes=10)), now=NOW)
    after = store.load()

    assert report.status is RuntimeStatus.BLOCKED
    assert report.reason == "session data is stale"
    assert after.cash == before.cash
    assert after.positions == before.positions
    assert after.open_incidents == 1

    runtime.run_once(session(captured_at=NOW - timedelta(minutes=10)), now=NOW)
    assert store.load().open_incidents == 1


def test_stop_is_persistent_and_prevents_new_sessions(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "runtime.json")
    runtime = PaperRuntime(store)
    runtime.start(NOW)
    runtime.stop(NOW, reason="operator requested")

    assert runtime.status().enabled is False
    assert runtime.run_once(session(), now=NOW).status is RuntimeStatus.STOPPED
