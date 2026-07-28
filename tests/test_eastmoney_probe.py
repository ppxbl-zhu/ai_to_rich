from quantagent.providers.eastmoney import (
    EastmoneyReadOnlyProbe,
    WindowDescriptor,
)


class FakeWindowEnumerator:
    def list_windows(self) -> tuple[WindowDescriptor, ...]:
        return (
            WindowDescriptor(
                title="东方财富终端",
                process_id=100,
                control_type_counts={"Pane": 5, "DataGrid": 1},
            ),
            WindowDescriptor(
                title="东方财富交易委托",
                process_id=101,
                control_type_counts={"Edit": 4, "Button": 8},
            ),
            WindowDescriptor(
                title="普通记事本",
                process_id=102,
                control_type_counts={"Edit": 1},
            ),
        )


def test_eastmoney_probe_only_returns_whitelisted_non_trading_windows() -> None:
    result = EastmoneyReadOnlyProbe().run(FakeWindowEnumerator())

    assert result.status == "available"
    assert result.windows == (
        WindowDescriptor(
            title="东方财富终端",
            process_id=100,
            control_type_counts={"Pane": 5, "DataGrid": 1},
        ),
    )


def test_eastmoney_probe_reports_unavailable_when_only_trading_window_exists() -> None:
    class TradingOnlyEnumerator:
        def list_windows(self) -> tuple[WindowDescriptor, ...]:
            return (
                WindowDescriptor(
                    title="东方财富账户资产",
                    process_id=101,
                    control_type_counts={"Text": 10},
                ),
            )

    result = EastmoneyReadOnlyProbe().run(TradingOnlyEnumerator())

    assert result.status == "unavailable"
    assert result.windows == ()
