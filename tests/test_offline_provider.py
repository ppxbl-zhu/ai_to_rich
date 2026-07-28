from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantagent.data import DataKind
from quantagent.providers.offline import OfflineProvider

CN_TZ = timezone(timedelta(hours=8))


def test_offline_provider_loads_multiple_data_kinds_without_network() -> None:
    provider = OfflineProvider(Path("tests/fixtures/point_in_time_dataset.json"))

    records = provider.fetch(
        kinds={
            DataKind.DAILY_BAR,
            DataKind.MINUTE_BAR,
            DataKind.FINANCIAL,
            DataKind.ANNOUNCEMENT,
            DataKind.NEWS,
            DataKind.INDEX,
            DataKind.SECTOR,
        },
        available_before=datetime(2026, 7, 29, 15, 0, tzinfo=CN_TZ),
    )

    assert {item.kind for item in records} == {
        DataKind.DAILY_BAR,
        DataKind.MINUTE_BAR,
        DataKind.FINANCIAL,
        DataKind.ANNOUNCEMENT,
        DataKind.NEWS,
        DataKind.INDEX,
        DataKind.SECTOR,
    }
    assert all(item.source == "offline-fixture" for item in records)
