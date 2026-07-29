from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quantagent.domain import Board, SecurityStatus
from quantagent.providers.eastmoney_ocr import (
    EastmoneyOcrCollector,
    OcrConflict,
    OcrFrame,
    OcrWord,
    parse_watchlist,
    reconcile_frames,
    reconcile_previous_closes,
    to_market_quotes,
    words_from_ocr_result,
)

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 9, 50, tzinfo=CST)


def word(text: str, x: int, y: int) -> OcrWord:
    return OcrWord(text=text, x=x, y=y, width=30, height=32)


def decimal_point(x: int, y: int) -> OcrWord:
    return OcrWord(text="·", x=x, y=y + 24, width=8, height=8)


def frame_words() -> tuple[OcrWord, ...]:
    return (
        word("300207", 113, 128),
        word("欣", 329, 128),
        word("旺", 379, 128),
        word("达", 429, 128),
        word("拿", 593, 128),
        word("18", 788, 128),
        decimal_point(836, 128),
        word("15", 848, 128),
        word("0", 957, 128),
        decimal_point(980, 128),
        word("95", 992, 128),
        word("300390", 113, 194),
        word("天", 329, 194),
        word("华", 379, 194),
        word("新", 429, 194),
        word("能", 479, 194),
        word("拿", 593, 194),
        word("53", 788, 194),
        decimal_point(836, 194),
        word("99", 848, 194),
        OcrWord(text="·", x=941, y=209, width=14, height=5),
        word("3", 956, 194),
        decimal_point(980, 194),
        word("98", 992, 194),
        word("002141", 113, 260),
        word("贤丰控股", 329, 260),
        word("6", 812, 260),
        decimal_point(836, 260),
        word("0", 848, 260),
        word("5", 956, 260),
        word("1", 1016, 260),
    )


def test_watchlist_parser_normalizes_prices_and_rejects_malformed_rows() -> None:
    quotes = parse_watchlist(frame_words(), captured_at=NOW)

    assert tuple((item.symbol, item.name) for item in quotes) == (
        ("300207.SZ", "欣旺达"),
        ("300390.SZ", "天华新能"),
    )
    assert quotes[0].price == Decimal("18.15")
    assert quotes[0].pct_change == Decimal("0.95")
    assert quotes[1].price == Decimal("53.99")
    assert quotes[1].pct_change == Decimal("-3.98")
    assert all(item.confidence == Decimal("0.50") for item in quotes)


def test_matching_frames_raise_confidence_and_conflicts_fail_closed() -> None:
    first = parse_watchlist(frame_words(), captured_at=NOW)
    second = parse_watchlist(frame_words(), captured_at=NOW + timedelta(seconds=1))

    reconciled = reconcile_frames(first, second)

    assert len(reconciled) == 2
    assert all(item.confidence == Decimal("0.80") for item in reconciled)
    assert all(item.confidence_method == "two_frame_consensus" for item in reconciled)

    changed = list(second)
    changed[0] = replace(changed[0], price=Decimal("18.16"))
    without_changed_symbol = reconcile_frames(first, tuple(changed))
    assert {item.symbol for item in without_changed_symbol} == {"300390.SZ"}


def test_collector_requires_safe_title_and_matching_layout() -> None:
    collector = EastmoneyOcrCollector()
    frame = OcrFrame(
        window_title="东方财富终端",
        window_width=1437,
        window_height=745,
        captured_at=NOW,
        words=frame_words(),
    )

    quotes = collector.collect(
        frame,
        replace(frame, captured_at=NOW + timedelta(seconds=1)),
    )
    assert len(quotes) == 2

    with pytest.raises(OcrConflict, match="safe market window"):
        collector.collect(
            replace(frame, window_title="东方财富交易委托"),
            replace(frame, captured_at=NOW + timedelta(seconds=1)),
        )
    with pytest.raises(OcrConflict, match="layout"):
        collector.collect(
            replace(frame, window_width=900),
            replace(frame, captured_at=NOW + timedelta(seconds=1)),
        )


def test_ocr_result_conversion_preserves_word_geometry() -> None:
    words = words_from_ocr_result(
        {
            "lines": [
                {
                    "words": [
                        {
                            "text": "300207",
                            "bounding_rect": {
                                "x": 113.2,
                                "y": 128.1,
                                "width": 140.0,
                                "height": 32.0,
                            },
                        }
                    ]
                }
            ]
        }
    )

    assert words == (OcrWord("300207", 113, 128, 140, 32),)


def test_tushare_previous_close_cross_check_promotes_only_matching_quotes() -> None:
    single_frame = parse_watchlist(frame_words(), captured_at=NOW)
    quotes = reconcile_frames(
        single_frame,
        parse_watchlist(frame_words(), captured_at=NOW + timedelta(seconds=1)),
    )

    verified = reconcile_previous_closes(
        quotes,
        {
            "300207.SZ": Decimal("17.98"),
            "300390.SZ": Decimal("50.00"),
        },
    )

    assert tuple(item.symbol for item in verified) == ("300207.SZ",)
    assert verified[0].confidence == Decimal("0.95")
    assert verified[0].confidence_method == "ocr_consensus+tushare_previous_close"

    single_verified = reconcile_previous_closes(
        single_frame,
        {"300207.SZ": Decimal("17.98")},
    )
    assert single_verified[0].confidence == Decimal("0.90")
    assert single_verified[0].confidence_method == "ocr_schema+tushare_previous_close"


def test_verified_ocr_quote_joins_tushare_limits_and_suspensions() -> None:
    verified = reconcile_previous_closes(
        parse_watchlist(frame_words(), captured_at=NOW),
        {"300207.SZ": Decimal("17.98")},
    )

    quotes = to_market_quotes(
        verified,
        previous_closes={"300207.SZ": Decimal("17.98")},
        price_limits={"300207.SZ": (Decimal("21.58"), Decimal("14.38"))},
        suspended_symbols=set(),
    )

    assert len(quotes) == 1
    assert quotes[0].symbol == "300207.SZ"
    assert quotes[0].board is Board.CHINEXT
    assert quotes[0].status is SecurityStatus.ACTIVE
    assert quotes[0].price == Decimal("18.15")
    assert quotes[0].source == "eastmoney-desktop-ocr+tushare"

    suspended = to_market_quotes(
        verified,
        previous_closes={"300207.SZ": Decimal("17.98")},
        price_limits={"300207.SZ": (Decimal("21.58"), Decimal("14.38"))},
        suspended_symbols={"300207.SZ"},
    )
    assert suspended[0].status is SecurityStatus.SUSPENDED
