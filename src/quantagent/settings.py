from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


class SettingsError(ValueError):
    """Raised when runtime settings violate a safety invariant."""


@dataclass(frozen=True, slots=True)
class Settings:
    execution_mode: str = "paper"
    database_url: str = "sqlite:///data/quantagent.db"
    market_data_mode: str = "offline"
    paper_state_path: str = "data/paper/runtime.json"
    eastmoney_read_only: bool = False
    tushare_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Settings:
        execution_mode = environ.get("QUANTAGENT_EXECUTION_MODE", "paper").lower()
        if execution_mode != "paper":
            raise SettingsError("execution mode must remain paper")
        market_data_mode = environ.get("QUANTAGENT_MARKET_DATA_MODE", "offline").lower()
        if market_data_mode not in {"offline", "tushare"}:
            raise SettingsError("market data mode must be offline or tushare")
        tushare_token = environ.get("TUSHARE_TOKEN") or None
        if market_data_mode == "tushare" and tushare_token is None:
            raise SettingsError("TUSHARE_TOKEN is required in tushare mode")
        eastmoney_read_only = _parse_bool(
            environ.get("QUANTAGENT_EASTMONEY_READ_ONLY", "false")
        )

        return cls(
            execution_mode=execution_mode,
            database_url=environ.get(
                "QUANTAGENT_DATABASE_URL", "sqlite:///data/quantagent.db"
            ),
            market_data_mode=market_data_mode,
            paper_state_path=environ.get(
                "QUANTAGENT_PAPER_STATE", "data/paper/runtime.json"
            ),
            eastmoney_read_only=eastmoney_read_only,
            tushare_token=tushare_token,
        )


def _parse_bool(value: str) -> bool:
    normalized = value.lower()
    if normalized not in {"true", "false"}:
        raise SettingsError("boolean settings must be true or false")
    return normalized == "true"
