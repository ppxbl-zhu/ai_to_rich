from __future__ import annotations

import pytest

from quantagent.settings import Settings, SettingsError


def test_settings_default_to_paper_mode_without_secrets() -> None:
    settings = Settings.from_env({})

    assert settings.execution_mode == "paper"
    assert settings.tushare_token is None
    assert settings.database_url == "sqlite:///data/quantagent.db"
    assert settings.market_data_mode == "offline"
    assert settings.paper_state_path == "data/paper/runtime.json"


def test_settings_reject_live_execution_mode() -> None:
    with pytest.raises(SettingsError, match="paper"):
        Settings.from_env({"QUANTAGENT_EXECUTION_MODE": "live"})


def test_settings_repr_does_not_expose_tokens() -> None:
    settings = Settings.from_env({"TUSHARE_TOKEN": "top-secret-token"})

    assert "top-secret-token" not in repr(settings)


def test_tushare_mode_requires_token_and_desktop_flag_is_explicit() -> None:
    with pytest.raises(SettingsError, match="TUSHARE_TOKEN"):
        Settings.from_env({"QUANTAGENT_MARKET_DATA_MODE": "tushare"})

    settings = Settings.from_env(
        {
            "QUANTAGENT_MARKET_DATA_MODE": "tushare",
            "TUSHARE_TOKEN": "top-secret-token",
            "QUANTAGENT_EASTMONEY_READ_ONLY": "true",
        }
    )
    assert settings.market_data_mode == "tushare"
    assert settings.eastmoney_read_only is True


def test_settings_reject_unknown_data_mode() -> None:
    with pytest.raises(SettingsError, match="market data mode"):
        Settings.from_env({"QUANTAGENT_MARKET_DATA_MODE": "unknown"})
