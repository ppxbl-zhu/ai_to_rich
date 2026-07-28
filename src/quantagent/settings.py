from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


class SettingsError(ValueError):
    """Raised when runtime settings violate a safety invariant."""


@dataclass(frozen=True, slots=True)
class Settings:
    execution_mode: str = "paper"
    database_url: str = "sqlite:///var/quantagent.db"
    tushare_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Settings:
        execution_mode = environ.get("QUANTAGENT_EXECUTION_MODE", "paper").lower()
        if execution_mode != "paper":
            raise SettingsError("execution mode must remain paper")

        return cls(
            execution_mode=execution_mode,
            database_url=environ.get(
                "QUANTAGENT_DATABASE_URL", "sqlite:///var/quantagent.db"
            ),
            tushare_token=environ.get("TUSHARE_TOKEN") or None,
        )
