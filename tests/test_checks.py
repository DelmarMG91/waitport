"""Tests for target parsing and single-shot readiness checks."""

from __future__ import annotations

import pytest

from helpers import free_port, http_server, open_tcp_port
from waitport.checks import CheckError, check_http, check_tcp, parse_status_range, parse_target


class TestParseTarget:
    """Target syntax coverage: accepted forms and rejected input."""

    def test_bare_host_port(self) -> None:
        target = parse_target("localhost:5432")
        assert target.kind == "tcp"
        assert target.host == "localhost"
        assert target.port == 5432
        assert target.url is None

    def test_tcp_scheme(self) -> None:
        target = parse_target("tcp://db.internal:6379")
        assert target.kind == "tcp"
        assert target.host == "db.internal"
        assert target.port == 6379

    def test_http_url_keeps_path(self) -> None:
        target = parse_target("http://api.local:8080/health?full=1")
        assert target.kind == "http"
        assert target.host == "api.local"
        assert target.port == 8080
        assert target.url == "http://api.local:8080/health?full=1"

    def test_https_default_port(self) -> None:
        target = parse_target("https://example.com/status")
        assert target.kind == "http"
        assert target.port == 443

    def test_http_default_port(self) -> None:
        target = parse_target("http://example.com")
        assert target.port == 80

    def test_ipv6_literal(self) -> None:
        target = parse_target("[::1]:9000")
        assert target.kind == "tcp"
        assert target.host == "::1"
        assert target.port == 9000

    def test_surrounding_whitespace_is_ignored(self) -> None:
        target = parse_target("  tcp://cache:11211  ")
        assert target.host == "cache"
        assert target.port == 11211

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "localhost",
            "localhost:",
            ":8080",
            "localhost:abc",
            "localhost:0",
            "localhost:70000",
            "tcp://localhost",
            "http://",
            "http://:8080/x",
        ],
    )
    def test_invalid_targets_raise(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_target(value)


class TestParseStatusRange:
    """HTTP status range parsing."""

    def test_range(self) -> None:
        assert parse_status_range("200-399") == (200, 399)

    def test_single_code(self) -> None:
        assert parse_status_range("204") == (204, 204)

    def test_whitespace(self) -> None:
        assert parse_status_range(" 300 - 399 ") == (300, 399)

    @pytest.mark.parametrize("value", ["", "abc", "200-", "-300", "399-200", "99-200", "200-600"])
    def test_invalid_ranges_raise(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_status_range(value)


class TestCheckTcp:
    """TCP connect checks against local sockets."""

    def test_success(self) -> None:
        with open_tcp_port() as port:
            assert check_tcp("127.0.0.1", port, timeout=1.0) is None

    def test_failure(self) -> None:
        port = free_port()
        with pytest.raises(CheckError):
            check_tcp("127.0.0.1", port, timeout=0.2)


class TestCheckHttp:
    """HTTP checks against a local ``http.server`` instance."""

    def test_200_is_ready(self) -> None:
        with http_server() as base:
            assert check_http(f"{base}/ok", timeout=2.0) is None

    def test_404_is_not_ready_by_default(self) -> None:
        with http_server() as base:
            with pytest.raises(CheckError) as excinfo:
                check_http(f"{base}/missing", timeout=2.0)
            assert "404" in str(excinfo.value)

    def test_404_accepted_by_custom_range(self) -> None:
        with http_server() as base:
            assert check_http(f"{base}/missing", status_min=400, status_max=499, timeout=2.0) is None

    def test_500_rejected(self) -> None:
        with http_server() as base:
            with pytest.raises(CheckError):
                check_http(f"{base}/error", timeout=2.0)

    def test_redirect_is_followed(self) -> None:
        with http_server() as base:
            assert check_http(f"{base}/redirect", timeout=2.0) is None
