from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WindowDescriptor:
    title: str
    process_id: int
    control_type_counts: Mapping[str, int]


class WindowEnumerator(Protocol):
    def list_windows(self) -> tuple[WindowDescriptor, ...]: ...


@dataclass(frozen=True, slots=True)
class DesktopProbeResult:
    status: str
    windows: tuple[WindowDescriptor, ...]


class EastmoneyReadOnlyProbe:
    _PRODUCT_MARKERS = ("东方财富", "东财")
    _FORBIDDEN_MARKERS = (
        "交易",
        "委托",
        "撤单",
        "账户",
        "资产",
        "持仓",
        "银证",
        "买入",
        "卖出",
    )

    @classmethod
    def is_safe_title(cls, title: str) -> bool:
        return any(marker in title for marker in cls._PRODUCT_MARKERS) and not any(
            marker in title for marker in cls._FORBIDDEN_MARKERS
        )

    def run(self, enumerator: WindowEnumerator) -> DesktopProbeResult:
        windows = tuple(
            window
            for window in enumerator.list_windows()
            if self.is_safe_title(window.title)
        )
        return DesktopProbeResult(
            status="available" if windows else "unavailable",
            windows=windows,
        )


class PywinautoWindowEnumerator:
    """Read only top-level titles and UIA control types; never invokes controls."""

    def list_windows(self) -> tuple[WindowDescriptor, ...]:
        from pywinauto import Desktop

        descriptors = []
        for window in Desktop(backend="uia").windows():
            title = window.window_text()
            if not EastmoneyReadOnlyProbe.is_safe_title(title):
                continue
            control_types = Counter(
                child.element_info.control_type for child in window.descendants()
            )
            descriptors.append(
                WindowDescriptor(
                    title=title,
                    process_id=window.process_id(),
                    control_type_counts=dict(sorted(control_types.items())),
                )
            )
        return tuple(descriptors)
