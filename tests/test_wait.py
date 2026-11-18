"""Tests for the concurrent wait loop."""

from __future__ import annotations

import time

import pytest

from helpers import free_port, http_server, open_tcp_port
from waitport.checks import parse_target
from waitport.wait import wait_for_targets


def test_all_targets_succeed() -> None:
    with open_tcp_port() as first, open_tcp_port() as second:
        results = wait_for_targets(
            [parse_target(f"127.0.0.1:{first}"), parse_target(f"127.0.0.1:{second}")],
            timeout=2.0,
            interval=0.05,
        )
    assert [result.ok for result in results] == [True, True]
    assert all(result.error is None for result in results)
    assert all(result.elapsed_ms >= 0 for result in results)


def test_single_target_times_out() -> None:
    port = free_port()
    started = time.monotonic()
    results = wait_for_targets(
        [parse_target(f"127.0.0.1:{port}")],
        timeout=0.3,
        interval=0.05,
    )
    elapsed = time.monotonic() - started
    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].error
    assert results[0].elapsed_ms >= 200
    assert elapsed < 2.0


def test_mixed_results_keep_input_order() -> None:
    with open_tcp_port() as ready_port:
        dead_port = free_port()
        results = wait_for_targets(
            [
                parse_target(f"127.0.0.1:{dead_port}"),
                parse_target(f"127.0.0.1:{ready_port}"),
            ],
            timeout=0.3,
            interval=0.05,
            concurrency=2,
        )
    assert [result.ok for result in results] == [False, True]
    assert results[0].target == f"127.0.0.1:{dead_port}"


def test_many_targets_with_concurrency() -> None:
    ports = []
    with open_tcp_port() as one, open_tcp_port() as two, open_tcp_port() as three:
        ports = [one, two, three]
        targets = [parse_target(f"tcp://127.0.0.1:{port}") for port in ports]
        results = wait_for_targets(targets, timeout=2.0, interval=0.05, concurrency=8)
    assert len(results) == 3
    assert all(result.ok for result in results)


def test_http_targets_are_supported() -> None:
    with http_server() as base:
        results = wait_for_targets(
            [parse_target(f"{base}/ok"), parse_target(f"{base}/missing")],
            timeout=0.3,
            interval=0.05,
            status_min=200,
            status_max=399,
        )
    assert [result.ok for result in results] == [True, False]
    assert "404" in (results[1].error or "")


def test_empty_target_list_returns_empty() -> None:
    assert wait_for_targets([], timeout=1.0) == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout": 0},
        {"timeout": -1},
        {"interval": 0},
        {"concurrency": 0},
    ],
)
def test_invalid_wait_arguments_raise(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        wait_for_targets([parse_target("127.0.0.1:1")], **kwargs)
