from __future__ import annotations

from quantagent.logging import redact_sensitive


def test_redaction_removes_nested_credentials_without_changing_safe_fields() -> None:
    event = {
        "event": "provider_check",
        "token": "secret-token",
        "nested": {"password": "secret-password", "provider": "offline"},
    }

    assert redact_sensitive(event) == {
        "event": "provider_check",
        "token": "[REDACTED]",
        "nested": {"password": "[REDACTED]", "provider": "offline"},
    }
