from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median

from quantagent.closing import ClosingCandidate


@dataclass(frozen=True, slots=True)
class RealtimeStock:
    symbol: str
    name: str
    price: Decimal
    pct_change_percent: Decimal
    volume_hands: Decimal
    amount: Decimal
    high: Decimal
    low: Decimal
    open: Decimal
    previous_close: Decimal
    volume_ratio: Decimal
    captured_at: datetime


def build_closing_candidates(
    rows: tuple[RealtimeStock, ...],
    *,
    memberships: Mapping[str, str],
    upper_limits: Mapping[str, Decimal],
    suspended_symbols: Set[str],
    observed_at: datetime,
) -> tuple[ClosingCandidate, ...]:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("closing observation requires a timezone")
    valid_context = tuple(item for item in rows if _valid_context_row(item))
    if not valid_context:
        raise ValueError("full-market realtime context is empty")
    market_return = median(item.pct_change_percent for item in valid_context)
    sector_returns: dict[str, list[Decimal]] = defaultdict(list)
    sector_advancers: dict[str, int] = defaultdict(int)
    for item in valid_context:
        sector = memberships.get(item.symbol)
        if sector is None:
            continue
        sector_returns[sector].append(item.pct_change_percent)
        if item.pct_change_percent > 0:
            sector_advancers[sector] += 1

    candidates = []
    for item in valid_context:
        sector = memberships.get(item.symbol)
        upper_limit = upper_limits.get(item.symbol)
        if (
            sector is None
            or upper_limit is None
            or item.symbol in suspended_symbols
            or _excluded_name(item.name)
            or item.high <= item.low
            or item.volume_hands <= 0
            or item.amount <= 0
        ):
            continue
        members = sector_returns[sector]
        vwap = item.amount / (item.volume_hands * Decimal(100))
        candidates.append(
            ClosingCandidate(
                symbol=item.symbol,
                observed_at=observed_at.timetz().replace(tzinfo=None),
                price=item.price,
                vwap=vwap,
                close_location=(item.price - item.low) / (item.high - item.low),
                volume_ratio=item.volume_ratio,
                turnover=item.amount,
                stock_relative_strength=(item.pct_change_percent - market_return)
                / Decimal(100),
                sector_relative_strength=(median(members) - market_return)
                / Decimal(100),
                sector_breadth=Decimal(sector_advancers[sector])
                / Decimal(len(members)),
                at_limit_up=item.price >= upper_limit,
                fresh=(
                    timedelta()
                    <= observed_at - item.captured_at
                    <= timedelta(seconds=60)
                    and item.captured_at.date() == observed_at.date()
                ),
            )
        )
    return tuple(sorted(candidates, key=lambda item: item.symbol))


def _valid_context_row(item: RealtimeStock) -> bool:
    return (
        item.price > 0
        and item.previous_close > 0
        and item.captured_at.tzinfo is not None
        and item.captured_at.utcoffset() is not None
    )


def _excluded_name(name: str) -> bool:
    normalized = name.strip().upper()
    return normalized.startswith(("ST", "*ST", "S*ST")) or "退" in normalized
