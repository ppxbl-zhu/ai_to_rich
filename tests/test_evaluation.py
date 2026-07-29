from datetime import date

from quantagent.evaluation import walk_forward_splits


def test_walk_forward_keeps_train_validation_and_test_chronological() -> None:
    dates = tuple(date(2026, 1, day) for day in range(1, 13))

    splits = walk_forward_splits(
        dates,
        train_size=4,
        validation_size=2,
        test_size=2,
        step=2,
    )

    assert splits[0].train == dates[0:4]
    assert splits[0].validation == dates[4:6]
    assert splits[0].test == dates[6:8]
    assert splits[1].train == dates[2:6]
    assert splits[1].validation == dates[6:8]
    assert splits[1].test == dates[8:10]
    assert all(
        max(split.train) < min(split.validation) < min(split.test) for split in splits
    )
