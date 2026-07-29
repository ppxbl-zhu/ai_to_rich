from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from quantagent.closing_snapshot import (
    RealtimeStock,
    build_closing_candidates,
)

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 14, 50, tzinfo=CST)


def stock(
    symbol: str,
    *,
    price: str,
    pct: str,
    high: str,
    low: str,
    amount: str = "120000000",
    volume_hands: str = "120000",
    volume_ratio: str = "1.8",
) -> RealtimeStock:
    return RealtimeStock(
        symbol=symbol,
        name=f"测试{symbol}",
        price=Decimal(price),
        pct_change_percent=Decimal(pct),
        volume_hands=Decimal(volume_hands),
        amount=Decimal(amount),
        high=Decimal(high),
        low=Decimal(low),
        open=Decimal(low),
        previous_close=Decimal("9"),
        volume_ratio=Decimal(volume_ratio),
        captured_at=NOW,
    )


def test_builds_closing_candidate_from_full_market_and_sector_context() -> None:
    rows = (
        stock("300001.SZ", price="10", pct="8", high="10", low="8"),
        stock("300002.SZ", price="9.5", pct="6", high="10", low="8"),
        stock("300003.SZ", price="8.5", pct="-1", high="10", low="8"),
        stock("600001.SH", price="9", pct="0", high="9.5", low="8.5"),
        stock("600002.SH", price="9", pct="0", high="9.5", low="8.5"),
    )
    memberships = {
        "300001.SZ": "801730.SI",
        "300002.SZ": "801730.SI",
        "300003.SZ": "801730.SI",
        "600001.SH": "801780.SI",
        "600002.SH": "801780.SI",
    }

    candidates = build_closing_candidates(
        rows,
        memberships=memberships,
        upper_limits={"300001.SZ": Decimal("10.80")},
        suspended_symbols=set(),
        observed_at=NOW,
    )

    candidate = next(item for item in candidates if item.symbol == "300001.SZ")
    assert candidate.vwap == Decimal("10")
    assert candidate.close_location == Decimal("1")
    assert candidate.stock_relative_strength == Decimal("0.08")
    assert candidate.sector_relative_strength == Decimal("0.06")
    assert candidate.sector_breadth == Decimal(2) / Decimal(3)
    assert candidate.at_limit_up is False
    assert candidate.fresh is True


def test_excludes_st_suspended_and_incomplete_realtime_rows() -> None:
    rows = (
        stock("300001.SZ", price="10", pct="8", high="10", low="8"),
        stock("300002.SZ", price="10", pct="8", high="10", low="10"),
        stock("300003.SZ", price="10", pct="8", high="10", low="8"),
    )
    rows = (
        rows[0],
        replace(rows[1], name="ST Test"),
        rows[2],
    )

    candidates = build_closing_candidates(
        rows,
        memberships={
            "300001.SZ": "801730.SI",
            "300002.SZ": "801730.SI",
            "300003.SZ": "801730.SI",
        },
        upper_limits={symbol: Decimal("12") for symbol in ("300001.SZ", "300003.SZ")},
        suspended_symbols={"300003.SZ"},
        observed_at=NOW,
    )

    assert tuple(item.symbol for item in candidates) == ("300001.SZ",)
