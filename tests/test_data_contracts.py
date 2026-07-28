from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quantagent.data import (
    DataConflict,
    DataContractError,
    DataKind,
    DataQuality,
    Dataset,
    PointInTimeRecord,
    reconcile,
)

CN_TZ = timezone(timedelta(hours=8))


def record(
    *,
    record_id: str = "daily:000001.SZ:20260728",
    available_at: datetime = datetime(2026, 7, 28, 17, 0, tzinfo=CN_TZ),
    source: str = "offline-a",
    close: str = "10.20",
) -> PointInTimeRecord:
    return PointInTimeRecord(
        record_id=record_id,
        kind=DataKind.DAILY_BAR,
        symbol="000001.SZ",
        event_time=datetime(2026, 7, 28, 15, 0, tzinfo=CN_TZ),
        available_at=available_at,
        captured_at=datetime(2026, 7, 28, 17, 1, tzinfo=CN_TZ),
        source=source,
        quality=DataQuality.VALID,
        payload={"close": close, "volume": 123456},
    )


def test_dataset_excludes_records_not_available_at_decision_time() -> None:
    dataset = Dataset([record()])

    assert dataset.available_at(datetime(2026, 7, 28, 16, 59, tzinfo=CN_TZ)) == ()
    assert dataset.available_at(datetime(2026, 7, 28, 17, 0, tzinfo=CN_TZ)) == (
        record(),
    )


def test_dataset_version_is_order_independent_and_changes_with_payload() -> None:
    first = record()
    second = record(
        record_id="daily:600000.SH:20260728",
        source="offline-b",
        close="8.20",
    )

    assert Dataset([first, second]).version == Dataset([second, first]).version
    assert Dataset([first]).version != Dataset([record(close="10.21")]).version


def test_reconciliation_rejects_silent_source_conflict() -> None:
    with pytest.raises(DataConflict, match="conflict"):
        reconcile(record(source="source-a"), record(source="source-b", close="10.21"))


def test_reconciliation_accepts_matching_values_and_records_both_sources() -> None:
    merged = reconcile(record(source="source-a"), record(source="source-b"))

    assert merged.quality is DataQuality.VALID
    assert merged.source == "source-a+source-b"
    assert merged.payload["close"] == "10.20"


def test_intraday_freshness_uses_market_event_time() -> None:
    intraday = PointInTimeRecord(
        record_id="minute:000001.SZ:202607291450",
        kind=DataKind.MINUTE_BAR,
        symbol="000001.SZ",
        event_time=datetime(2026, 7, 29, 14, 50, tzinfo=CN_TZ),
        available_at=datetime(2026, 7, 29, 14, 50, 3, tzinfo=CN_TZ),
        captured_at=datetime(2026, 7, 29, 14, 50, 4, tzinfo=CN_TZ),
        source="desktop",
        quality=DataQuality.VALID,
        payload={"close": Decimal("10.00")},
    )

    assert intraday.is_fresh(
        datetime(2026, 7, 29, 14, 50, 30, tzinfo=CN_TZ),
        max_age=timedelta(seconds=30),
    )
    assert not intraday.is_fresh(
        datetime(2026, 7, 29, 14, 50, 31, tzinfo=CN_TZ),
        max_age=timedelta(seconds=30),
    )


def test_point_in_time_record_rejects_naive_timestamps() -> None:
    with pytest.raises(DataContractError, match="timezone"):
        PointInTimeRecord(
            record_id="bad",
            kind=DataKind.NEWS,
            symbol="MARKET",
            event_time=datetime(2026, 7, 29, 10, 0),
            available_at=datetime(2026, 7, 29, 10, 0, tzinfo=CN_TZ),
            captured_at=datetime(2026, 7, 29, 10, 1, tzinfo=CN_TZ),
            source="offline",
            quality=DataQuality.VALID,
            payload={"title": "bad"},
        )


def test_point_in_time_record_rejects_capture_before_availability() -> None:
    with pytest.raises(DataContractError, match="captured"):
        PointInTimeRecord(
            record_id="bad",
            kind=DataKind.NEWS,
            symbol="MARKET",
            event_time=datetime(2026, 7, 29, 10, 0, tzinfo=CN_TZ),
            available_at=datetime(2026, 7, 29, 10, 1, tzinfo=CN_TZ),
            captured_at=datetime(2026, 7, 29, 10, 0, tzinfo=CN_TZ),
            source="offline",
            quality=DataQuality.VALID,
            payload={"title": "bad"},
        )


def test_dataset_rejects_duplicate_record_ids() -> None:
    with pytest.raises(DataContractError, match="duplicate"):
        Dataset([record(), record()])


def test_point_in_time_payload_cannot_mutate_after_creation() -> None:
    item = record()

    with pytest.raises(TypeError):
        item.payload["close"] = "99.99"
