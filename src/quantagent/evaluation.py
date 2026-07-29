from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class WalkForwardSplit:
    train: tuple[date, ...]
    validation: tuple[date, ...]
    test: tuple[date, ...]


def walk_forward_splits(
    dates: tuple[date, ...],
    *,
    train_size: int,
    validation_size: int,
    test_size: int,
    step: int,
) -> tuple[WalkForwardSplit, ...]:
    sizes = (train_size, validation_size, test_size, step)
    if any(size <= 0 for size in sizes):
        raise ValueError("walk-forward window sizes and step must be positive")
    if tuple(sorted(dates)) != dates or len(set(dates)) != len(dates):
        raise ValueError("dates must be strictly increasing")

    window_size = train_size + validation_size + test_size
    splits: list[WalkForwardSplit] = []
    for start in range(0, len(dates) - window_size + 1, step):
        train_end = start + train_size
        validation_end = train_end + validation_size
        test_end = validation_end + test_size
        splits.append(
            WalkForwardSplit(
                train=dates[start:train_end],
                validation=dates[train_end:validation_end],
                test=dates[validation_end:test_end],
            )
        )
    return tuple(splits)
