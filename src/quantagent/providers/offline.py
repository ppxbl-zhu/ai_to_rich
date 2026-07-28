from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from quantagent.data import DataKind, DataQuality, PointInTimeRecord


class OfflineProvider:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def fetch(
        self, *, kinds: set[DataKind], available_before: datetime
    ) -> tuple[PointInTimeRecord, ...]:
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        records = (
            PointInTimeRecord(
                record_id=item["record_id"],
                kind=DataKind(item["kind"]),
                symbol=item["symbol"],
                event_time=datetime.fromisoformat(item["event_time"]),
                available_at=datetime.fromisoformat(item["available_at"]),
                captured_at=datetime.fromisoformat(item["captured_at"]),
                source=item["source"],
                quality=DataQuality(item["quality"]),
                payload=item["payload"],
            )
            for item in payload["records"]
        )
        return tuple(
            record
            for record in records
            if record.kind in kinds
            and record.available_at <= available_before
            and record.quality is DataQuality.VALID
        )
