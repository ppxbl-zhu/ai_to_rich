from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Bar


@dataclass(frozen=True)
class TrendSetup:
    score: float
    phase: str
    trend_structure: float
    compression: float
    accumulation: float
    breakout_quality: float
    extension_penalty: float

    def as_dict(self) -> dict:
        return asdict(self)


def _volatility(closes: list[float]) -> float:
    returns = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    return math.sqrt(sum(value * value for value in returns) / len(returns)) if returns else 0.0


def main_rise_setup(bars: list[Bar]) -> TrendSetup:
    if len(bars) < 80:
        return TrendSetup(-1.0, "样本不足", 0, 0, 0, 0, 0)
    closes = [bar.close for bar in bars]
    close = closes[-1]
    ma20 = statistics.mean(closes[-20:])
    ma60 = statistics.mean(closes[-60:])
    previous_ma20 = statistics.mean(closes[-25:-5])
    high60 = max(bar.high for bar in bars[-60:])
    previous_high20 = max(bar.high for bar in bars[-21:-1])
    trend_structure = sum((close > ma20, ma20 > ma60, ma20 > previous_ma20)) / 3
    recent_volatility = _volatility(closes[-11:])
    earlier_volatility = _volatility(closes[-31:-10])
    compression = max(-1.0, min(1.0, 1 - recent_volatility / earlier_volatility)) if earlier_volatility else 0.0
    up_volume = sum(bar.volume for previous, bar in zip(bars[-21:-1], bars[-20:]) if bar.close >= previous.close)
    down_volume = sum(bar.volume for previous, bar in zip(bars[-21:-1], bars[-20:]) if bar.close < previous.close)
    accumulation = max(-1.0, min(1.0, (up_volume - down_volume) / max(1.0, up_volume + down_volume)))
    near_high = max(0.0, 1 - (high60 - close) / max(close, 1e-9) / .12)
    breakout = 1.0 if close > previous_high20 else max(0.0, 1 - (previous_high20 - close) / max(close, 1e-9) / .05)
    recent_volume = statistics.mean(bar.volume for bar in bars[-5:])
    baseline_volume = statistics.mean(bar.volume for bar in bars[-25:-5])
    volume_confirmation = max(0.0, min(1.0, recent_volume / baseline_volume - 1)) if baseline_volume else 0.0
    breakout_quality = .45 * near_high + .35 * breakout + .20 * volume_confirmation
    extension = close / ma20 - 1 if ma20 > 0 else 0.0
    extension_penalty = max(0.0, min(1.0, (extension - .08) / .12))
    score = .35 * trend_structure + .15 * compression + .20 * accumulation + .30 * breakout_quality - .35 * extension_penalty
    if close < ma20 or ma20 < ma60:
        phase = "趋势衰减"
    elif breakout >= .98 and volume_confirmation > .15:
        phase = "主升持有"
    elif near_high >= .75 and breakout >= .65:
        phase = "突破待确认"
    elif trend_structure >= .99 and compression > .15:
        phase = "蓄势观察"
    else:
        phase = "趋势观察"
    return TrendSetup(score, phase, trend_structure, compression, accumulation, breakout_quality, extension_penalty)
