import json
from pathlib import Path

from quantagent.paper_cli import main

NOW = "2026-07-29T14:50:10+08:00"


def test_cli_start_run_once_status_and_stop(tmp_path: Path, capsys: object) -> None:
    state_path = tmp_path / "paper-runtime.json"

    assert main(["--state", str(state_path), "start", "--at", NOW]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    assert (
        main(
            [
                "--state",
                str(state_path),
                "run-once",
                "--session",
                "tests/fixtures/paper_session.json",
                "--at",
                NOW,
            ]
        )
        == 0
    )
    run_report = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert run_report == {
        "dataset_version": "sha256:offline-paper-session",
        "fills": 2,
        "generated_plans": 2,
        "reason": None,
        "rejected_plans": 0,
        "session_id": "offline-session-20260729-1450",
        "status": "completed",
    }

    assert main(["--state", str(state_path), "status"]) == 0
    status = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert status["enabled"] is True
    assert status["cash"] == "86389.86"
    assert status["positions"] == {"000001.SZ": 800, "300001.SZ": 200}

    assert (
        main(
            [
                "--state",
                str(state_path),
                "stop",
                "--at",
                NOW,
                "--reason",
                "operator requested",
            ]
        )
        == 0
    )
    stopped = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert stopped["enabled"] is False
