from quantagent.providers.eastmoney import (
    EastmoneyReadOnlyProbe,
    WindowDescriptor,
)


class FakeWindowEnumerator:
    def list_windows(self) -> tuple[WindowDescriptor, ...]:
        return (
            WindowDescriptor(
                title="\u4e1c\u65b9\u8d22\u5bcc\u7ec8\u7aef",
                process_id=100,
                control_type_counts={"Pane": 5, "DataGrid": 1},
            ),
            WindowDescriptor(
                title="\u4e1c\u65b9\u8d22\u5bcc\u4ea4\u6613\u59d4\u6258",
                process_id=101,
                control_type_counts={"Edit": 4, "Button": 8},
            ),
            WindowDescriptor(
                title="\u666e\u901a\u8bb0\u4e8b\u672c",
                process_id=102,
                control_type_counts={"Edit": 1},
            ),
        )


def test_eastmoney_probe_only_returns_whitelisted_non_trading_windows() -> None:
    result = EastmoneyReadOnlyProbe().run(FakeWindowEnumerator())

    assert result.status == "available"
    assert result.windows == (
        WindowDescriptor(
            title="\u4e1c\u65b9\u8d22\u5bcc\u7ec8\u7aef",
            process_id=100,
            control_type_counts={"Pane": 5, "DataGrid": 1},
        ),
    )


def test_eastmoney_probe_reports_unavailable_when_only_trading_window_exists() -> None:
    class TradingOnlyEnumerator:
        def list_windows(self) -> tuple[WindowDescriptor, ...]:
            return (
                WindowDescriptor(
                    title="\u4e1c\u65b9\u8d22\u5bcc\u8d26\u6237\u8d44\u4ea7",
                    process_id=101,
                    control_type_counts={"Text": 10},
                ),
            )

    result = EastmoneyReadOnlyProbe().run(TradingOnlyEnumerator())

    assert result.status == "unavailable"
    assert result.windows == ()
