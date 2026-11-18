"""Tests for the command line interface."""

from __future__ import annotations

import json

import pytest

from helpers import free_port, http_server, open_tcp_port
from waitport.cli import main


def test_json_result_structure(capsys: pytest.CaptureFixture) -> None:
    with open_tcp_port() as port:
        code = main([f"127.0.0.1:{port}", "--json", "--timeout", "2", "--interval", "0.05"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    record = payload[0]
    assert set(record) == {"target", "ok", "elapsed_ms", "error"}
    assert record["target"] == f"127.0.0.1:{port}"
    assert record["ok"] is True
    assert record["error"] is None
    assert isinstance(record["elapsed_ms"], int)


def test_json_failure_record(capsys: pytest.CaptureFixture) -> None:
    port = free_port()
    code = main([f"127.0.0.1:{port}", "--json", "--timeout", "0.3", "--interval", "0.05"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["ok"] is False
    assert payload[0]["error"]


def test_human_output_lists_each_target(capsys: pytest.CaptureFixture) -> None:
    with open_tcp_port() as first, open_tcp_port() as second:
        code = main(
            [
                f"127.0.0.1:{first}",
                f"127.0.0.1:{second}",
                "--timeout",
                "2",
                "--interval",
                "0.05",
            ]
        )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.count("[ok]") == 2
    assert "all 2 target(s) ready" in captured.out


def test_quiet_mode_prints_only_summary(capsys: pytest.CaptureFixture) -> None:
    with open_tcp_port() as port:
        code = main([f"127.0.0.1:{port}", "--quiet", "--timeout", "2", "--interval", "0.05"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip().startswith("ready: 1 target(s) in ")
    assert "[ok]" not in captured.out


def test_quiet_mode_failure_summary(capsys: pytest.CaptureFixture) -> None:
    port = free_port()
    code = main([f"127.0.0.1:{port}", "--quiet", "--timeout", "0.3", "--interval", "0.05"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out.strip() == "not ready: 1 of 1 target(s)"


def test_http_target_success(capsys: pytest.CaptureFixture) -> None:
    with http_server() as base:
        code = main([f"{base}/ok", "--json", "--timeout", "2", "--interval", "0.05"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)[0]["ok"] is True


def test_custom_http_status_range(capsys: pytest.CaptureFixture) -> None:
    with http_server() as base:
        code = main(
            [
                f"{base}/missing",
                "--http-status",
                "400-499",
                "--json",
                "--timeout",
                "2",
                "--interval",
                "0.05",
            ]
        )
    assert code == 0
    assert json.loads(capsys.readouterr().out)[0]["ok"] is True


def test_invalid_target_returns_usage_error(capsys: pytest.CaptureFixture) -> None:
    code = main(["not-a-target"])
    captured = capsys.readouterr()
    assert code == 2
    assert "error" in captured.err.lower()


def test_invalid_status_range_returns_usage_error(capsys: pytest.CaptureFixture) -> None:
    with open_tcp_port() as port:
        code = main([f"127.0.0.1:{port}", "--http-status", "banana"])
    assert code == 2
    assert "status range" in capsys.readouterr().err.lower()


def test_version_flag_prints_version(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert "waitport" in output
    assert "0.1.0" in output
