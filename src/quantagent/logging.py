from __future__ import annotations

from typing import Any

_SENSITIVE_KEYS = frozenset(
    {"api_key", "authorization", "cookie", "password", "secret", "token"}
)


def redact_sensitive(event: dict[str, Any]) -> dict[str, Any]:
    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    return redact(event)
