from __future__ import annotations

import pytest

from quantagent.settings import Settings, SettingsError


def test_settings_default_to_paper_mode_without_secrets() -> None:
    settings = Settings.from_env({})

    assert settings.execution_mode == "paper"
    assert settings.tushare_token is None
    assert settings.database_url == "sqlite:///var/quantagent.db"


def test_settings_reject_live_execution_mode() -> None:
    with pytest.raises(SettingsError, match="paper"):
        Settings.from_env({"QUANTAGENT_EXECUTION_MODE": "live"})


def test_settings_repr_does_not_expose_tokens() -> None:
    settings = Settings.from_env({"TUSHARE_TOKEN": "top-secret-token"})

    assert "top-secret-token" not in repr(settings)
