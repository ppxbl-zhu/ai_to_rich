from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from quantagent.domain import Board, MarketQuote, SecurityStatus
from quantagent.providers.eastmoney import EastmoneyReadOnlyProbe


class OcrConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OcrWord:
    text: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class OcrFrame:
    window_title: str
    window_width: int
    window_height: int
    captured_at: datetime
    words: tuple[OcrWord, ...]


@dataclass(frozen=True, slots=True)
class EastmoneyOcrQuote:
    symbol: str
    name: str
    price: Decimal
    pct_change: Decimal
    captured_at: datetime
    source: str = "eastmoney-desktop-ocr"
    confidence: Decimal = Decimal("0.50")
    confidence_method: str = "single_frame_schema_validation"


class EastmoneyOcrCollector:
    _MINIMUM_WIDTH = 1300
    _MAXIMUM_WIDTH = 1600
    _MINIMUM_HEIGHT = 680
    _MAXIMUM_HEIGHT = 850

    def collect(
        self, first: OcrFrame, second: OcrFrame
    ) -> tuple[EastmoneyOcrQuote, ...]:
        if not EastmoneyReadOnlyProbe.is_safe_title(first.window_title):
            raise OcrConflict("OCR capture is not a safe market window")
        if first.window_title != second.window_title:
            raise OcrConflict("window title changed between OCR frames")
        if not self._layout_allowed(first) or not self._layout_allowed(second):
            raise OcrConflict(
                "Eastmoney window layout is outside the approved baseline"
            )
        if (
            first.window_width != second.window_width
            or first.window_height != second.window_height
        ):
            raise OcrConflict("Eastmoney window layout changed between frames")
        return reconcile_frames(
            parse_watchlist(first.words, captured_at=first.captured_at),
            parse_watchlist(second.words, captured_at=second.captured_at),
        )

    def _layout_allowed(self, frame: OcrFrame) -> bool:
        return (
            self._MINIMUM_WIDTH <= frame.window_width <= self._MAXIMUM_WIDTH
            and self._MINIMUM_HEIGHT <= frame.window_height <= self._MAXIMUM_HEIGHT
        )


class WindowsEastmoneyFrameSource:
    _WATCHLIST_BOX = (0.0487, 0.6711, 0.3758, 0.9396)
    _OCR_SIZE = (1410, 600)

    def capture(self, process_id: int) -> OcrFrame:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        from pywinauto import Application
        from winocr import recognize_pil_sync

        window = Application(backend="uia").connect(process=process_id).top_window()
        title = window.window_text()
        if not EastmoneyReadOnlyProbe.is_safe_title(title):
            raise OcrConflict("OCR capture is not a safe market window")
        image = window.capture_as_image()
        if image is None:
            raise OcrConflict("Eastmoney window capture failed")
        width, height = image.size
        left, top, right, bottom = self._WATCHLIST_BOX
        crop = image.crop(
            (
                round(width * left),
                round(height * top),
                round(width * right),
                round(height * bottom),
            )
        )
        crop = crop.resize(self._OCR_SIZE, Image.Resampling.LANCZOS)
        crop = ImageEnhance.Contrast(crop).enhance(1.4)
        crop = crop.filter(ImageFilter.SHARPEN)
        crop = ImageOps.exif_transpose(crop)
        result = recognize_pil_sync(crop, "zh-Hans-CN")
        return OcrFrame(
            window_title=title,
            window_width=width,
            window_height=height,
            captured_at=datetime.now().astimezone(),
            words=words_from_ocr_result(result),
        )


def words_from_ocr_result(result: Mapping[str, Any]) -> tuple[OcrWord, ...]:
    words = []
    for line in result.get("lines", []):
        for item in line.get("words", []):
            rectangle = item["bounding_rect"]
            words.append(
                OcrWord(
                    text=str(item["text"]),
                    x=round(rectangle["x"]),
                    y=round(rectangle["y"]),
                    width=round(rectangle["width"]),
                    height=round(rectangle["height"]),
                )
            )
    return tuple(words)


def parse_watchlist(
    words: tuple[OcrWord, ...], *, captured_at: datetime
) -> tuple[EastmoneyOcrQuote, ...]:
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("capture timestamp must include a timezone")
    code_words = sorted(
        (item for item in words if re.fullmatch(r"\d{6}", item.text) and item.x < 300),
        key=lambda item: item.y,
    )
    quotes = []
    for code_word in code_words:
        row_center = code_word.y + code_word.height / 2
        row = tuple(
            item
            for item in words
            if abs((item.y + item.height / 2) - row_center) <= 20
            and item is not code_word
        )
        name = "".join(
            item.text
            for item in sorted(row, key=lambda item: item.x)
            if 300 <= item.x < 560
        ).strip()
        price = _decimal_from_words(row, minimum_x=740, maximum_x=920)
        pct_change = _decimal_from_words(
            row, minimum_x=920, maximum_x=1050, signed=True
        )
        if (
            not name
            or price is None
            or pct_change is None
            or not Decimal() < price < Decimal("10000")
            or abs(pct_change) > Decimal("30")
        ):
            continue
        symbol = _market_symbol(code_word.text)
        if symbol is None:
            continue
        quotes.append(
            EastmoneyOcrQuote(
                symbol=symbol,
                name=name,
                price=price,
                pct_change=pct_change,
                captured_at=captured_at,
            )
        )
    return tuple(quotes)


def reconcile_frames(
    first: tuple[EastmoneyOcrQuote, ...],
    second: tuple[EastmoneyOcrQuote, ...],
) -> tuple[EastmoneyOcrQuote, ...]:
    first_by_symbol = {item.symbol: item for item in first}
    second_by_symbol = {item.symbol: item for item in second}
    reconciled = []
    for symbol in sorted(set(first_by_symbol) & set(second_by_symbol)):
        earlier = first_by_symbol[symbol]
        later = second_by_symbol[symbol]
        if (
            earlier.name != later.name
            or earlier.price != later.price
            or earlier.pct_change != later.pct_change
        ):
            continue
        reconciled.append(
            replace(
                later,
                confidence=Decimal("0.80"),
                confidence_method="two_frame_consensus",
            )
        )
    if not reconciled:
        raise OcrConflict("OCR frames have no matching quotes")
    return tuple(reconciled)


def reconcile_previous_closes(
    quotes: tuple[EastmoneyOcrQuote, ...],
    previous_closes: Mapping[str, Decimal],
    *,
    tolerance_percentage_points: Decimal = Decimal("0.15"),
) -> tuple[EastmoneyOcrQuote, ...]:
    verified = []
    for quote in quotes:
        previous_close = previous_closes.get(quote.symbol)
        if previous_close is None or previous_close <= 0:
            continue
        calculated = (quote.price / previous_close - Decimal(1)) * Decimal(100)
        if abs(calculated - quote.pct_change) > tolerance_percentage_points:
            continue
        has_consensus = quote.confidence_method == "two_frame_consensus"
        verified.append(
            replace(
                quote,
                confidence=Decimal("0.95") if has_consensus else Decimal("0.90"),
                confidence_method=(
                    "ocr_consensus+tushare_previous_close"
                    if has_consensus
                    else "ocr_schema+tushare_previous_close"
                ),
            )
        )
    if not verified:
        raise OcrConflict("no OCR quotes match Tushare previous closes")
    return tuple(verified)


def to_market_quotes(
    quotes: tuple[EastmoneyOcrQuote, ...],
    *,
    previous_closes: Mapping[str, Decimal],
    price_limits: Mapping[str, tuple[Decimal, Decimal]],
    suspended_symbols: set[str],
) -> tuple[MarketQuote, ...]:
    market_quotes = []
    for quote in quotes:
        previous_close = previous_closes.get(quote.symbol)
        limits = price_limits.get(quote.symbol)
        board = _board(quote.symbol)
        if (
            quote.confidence < Decimal("0.90")
            or previous_close is None
            or limits is None
            or board is None
        ):
            continue
        market_quotes.append(
            MarketQuote(
                symbol=quote.symbol,
                name=quote.name,
                board=board,
                market_time=quote.captured_at,
                captured_at=quote.captured_at,
                price=quote.price,
                previous_close=previous_close,
                limit_up=limits[0],
                limit_down=limits[1],
                status=(
                    SecurityStatus.SUSPENDED
                    if quote.symbol in suspended_symbols
                    else SecurityStatus.ACTIVE
                ),
                source="eastmoney-desktop-ocr+tushare",
            )
        )
    if not market_quotes:
        raise OcrConflict("no OCR quotes have complete Tushare risk metadata")
    return tuple(market_quotes)


def _decimal_from_words(
    words: tuple[OcrWord, ...],
    *,
    minimum_x: int,
    maximum_x: int,
    signed: bool = False,
) -> Decimal | None:
    raw = "".join(
        item.text
        for item in sorted(words, key=lambda item: item.x)
        if minimum_x <= item.x < maximum_x
    )
    normalized = (
        raw.replace(" ", "")
        .replace("\uff0e", ".")
        .replace("·", ".")
        .replace("。", ".")
        .replace("%", "")
        .replace("\uff05", "")
    )
    if signed and normalized.startswith("."):
        normalized = f"-{normalized[1:]}"
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", normalized):
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _market_symbol(code: str) -> str | None:
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return None


def _board(symbol: str) -> Board | None:
    code = symbol.split(".", maxsplit=1)[0]
    if code.startswith("3"):
        return Board.CHINEXT
    if code.startswith(("688", "689")):
        return Board.STAR
    if code.startswith(("0", "6")):
        return Board.MAIN
    return None
