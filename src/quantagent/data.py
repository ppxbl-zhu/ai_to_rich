from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class DataKind(StrEnum):
    DAILY_BAR = "daily_bar"
    MINUTE_BAR = "minute_bar"
    INDEX = "index"
    SECTOR = "sector"
    FINANCIAL = "financial"
    ANNOUNCEMENT = "announcement"
    NEWS = "news"


class DataQuality(StrEnum):
    VALID = "valid"
    STALE = "stale"
    CONFLICT = "conflict"
    ERROR = "error"


class DataConflict(ValueError):
    """Raised when sources disagree and no deterministic winner exists."""


class DataContractError(ValueError):
    """Raised when a record cannot be used in point-in-time research."""


@dataclass(frozen=True, slots=True)
class PointInTimeRecord:
    record_id: str
    kind: DataKind
    symbol: str
    event_time: datetime
    available_at: datetime
    captured_at: datetime
    source: str
    quality: DataQuality
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        timestamps = (self.event_time, self.available_at, self.captured_at)
        if any(item.tzinfo is None or item.utcoffset() is None for item in timestamps):
            raise DataContractError("all timestamps require timezone information")
        if self.available_at < self.event_time:
            raise DataContractError("availability cannot precede the event")
        if self.captured_at < self.available_at:
            raise DataContractError("captured time cannot precede availability")
        object.__setattr__(self, "payload", _freeze(self.payload))

    def is_fresh(self, decision_time: datetime, *, max_age: timedelta) -> bool:
        age = decision_time - self.event_time
        return self.quality is DataQuality.VALID and timedelta() <= age <= max_age


class Dataset:
    def __init__(self, records: list[PointInTimeRecord]) -> None:
        record_ids = [record.record_id for record in records]
        if len(record_ids) != len(set(record_ids)):
            raise DataContractError("duplicate record id in dataset")
        self.records = tuple(records)

    @property
    def version(self) -> str:
        serialized = [
            {
                "record_id": record.record_id,
                "kind": record.kind.value,
                "symbol": record.symbol,
                "event_time": record.event_time.isoformat(),
                "available_at": record.available_at.isoformat(),
                "captured_at": record.captured_at.isoformat(),
                "source": record.source,
                "quality": record.quality.value,
                "payload": record.payload,
            }
            for record in sorted(self.records, key=lambda item: item.record_id)
        ]
        canonical = json.dumps(
            serialized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
        return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"

    def available_at(self, decision_time: datetime) -> tuple[PointInTimeRecord, ...]:
        return tuple(
            record
            for record in self.records
            if record.available_at <= decision_time
            and record.quality is DataQuality.VALID
        )


def reconcile(first: PointInTimeRecord, second: PointInTimeRecord) -> PointInTimeRecord:
    if (
        first.record_id != second.record_id
        or first.kind is not second.kind
        or first.symbol != second.symbol
        or first.payload != second.payload
    ):
        raise DataConflict("source conflict requires explicit review")
    sources = "+".join(sorted({first.source, second.source}))
    return replace(
        first,
        available_at=max(first.available_at, second.available_at),
        captured_at=max(first.captured_at, second.captured_at),
        source=sources,
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"unsupported dataset value: {type(value).__name__}")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
