"""Target parsing and individual readiness checks.

This module is intentionally free of any concurrency logic. It exposes:

* :func:`parse_target` - turn a user supplied target string into a :class:`Target`.
* :func:`parse_status_range` - parse ``"200-399"`` style HTTP status ranges.
* :func:`check_tcp` - a single TCP connect attempt.
* :func:`check_http` - a single HTTP(S) request attempt.

The ``check_*`` helpers return ``None`` on success and raise :class:`CheckError`
on failure so callers can surface a human readable reason.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

__all__ = [
    "DEFAULT_TIMEOUT",
    "CheckError",
    "Target",
    "parse_target",
    "parse_status_range",
    "check_tcp",
    "check_http",
]

#: Default per-attempt socket/request timeout, in seconds.
DEFAULT_TIMEOUT: float = 1.0

#: User agent sent with HTTP probes so server logs identify the client.
_USER_AGENT = "waitport/0.1.0"


class CheckError(Exception):
    """Raised when a single readiness check fails."""


@dataclass(frozen=True)
class Target:
    """A parsed wait target.

    Attributes:
        raw: The original string supplied by the user.
        kind: Either ``"tcp"`` or ``"http"``.
        host: The host name or IP address.
        port: The TCP port number.
        url: The fully qualified URL for HTTP targets, else ``None``.
    """

    raw: str
    kind: str
    host: str
    port: int
    url: Optional[str] = None


def _split_host_port(spec: str, raw: str) -> Tuple[str, int]:
    """Split a ``host:port`` string into its components.

    Supports bracketed IPv6 literals such as ``[::1]:8080``.
    """
    if spec.startswith("["):
        end = spec.find("]")
        if end == -1:
            raise ValueError(f"invalid IPv6 target (missing ']'): {raw!r}")
        host = spec[1:end]
        remainder = spec[end + 1 :]
        if not remainder.startswith(":"):
            raise ValueError(f"target must be host:port, got {raw!r}")
        port_str = remainder[1:]
        if not host:
            raise ValueError(f"empty host in target: {raw!r}")
    else:
        if spec.count(":") != 1:
            raise ValueError(f"target must be host:port, got {raw!r}")
        host, port_str = spec.rsplit(":", 1)
        if not host:
            raise ValueError(f"empty host in target: {raw!r}")

    try:
        port = int(port_str)
    except (TypeError, ValueError):
        raise ValueError(f"invalid port in target: {raw!r}") from None
    if not 0 < port < 65536:
        raise ValueError(f"port out of range in target: {raw!r}")
    return host, port


def parse_target(raw: str) -> Target:
    """Parse a single target string.

    Accepted forms::

        host:port
        tcp://host:port
        http://host[:port][/path]
        https://host[:port][/path]

    Args:
        raw: The target string to parse.

    Returns:
        A :class:`Target` describing the endpoint.

    Raises:
        ValueError: If ``raw`` is empty or not a recognised target form.
    """
    if not isinstance(raw, str):
        raise ValueError(f"target must be a string, got {type(raw).__name__}")
    spec = raw.strip()
    if not spec:
        raise ValueError("target must not be empty")

    lowered = spec.lower()
    if lowered.startswith("tcp://"):
        host, port = _split_host_port(spec[len("tcp://") :], raw)
        return Target(raw=raw, kind="tcp", host=host, port=port)

    if lowered.startswith("http://") or lowered.startswith("https://"):
        parsed = urllib.parse.urlsplit(spec)
        if not parsed.hostname:
            raise ValueError(f"invalid URL target: {raw!r}")
        try:
            port = parsed.port
        except ValueError:
            raise ValueError(f"invalid port in URL target: {raw!r}") from None
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        return Target(
            raw=raw,
            kind="http",
            host=parsed.hostname,
            port=port,
            url=spec,
        )

    host, port = _split_host_port(spec, raw)
    return Target(raw=raw, kind="tcp", host=host, port=port)


def parse_status_range(value: str) -> Tuple[int, int]:
    """Parse an HTTP status range like ``"200-399"`` or a single code ``"200"``.

    Args:
        value: The range expression to parse.

    Returns:
        A ``(low, high)`` tuple of integers, inclusive.

    Raises:
        ValueError: If the expression is malformed or out of the 100-599 range.
    """
    if not isinstance(value, str):
        raise ValueError("status range must be a string")
    text = value.strip()
    if not text:
        raise ValueError("status range must not be empty")

    if "-" in text:
        low_str, _, high_str = text.partition("-")
        low_str, high_str = low_str.strip(), high_str.strip()
        if not low_str or not high_str:
            raise ValueError(f"invalid status range: {value!r}")
        try:
            low, high = int(low_str), int(high_str)
        except ValueError:
            raise ValueError(f"invalid status range: {value!r}") from None
    else:
        try:
            low = high = int(text)
        except ValueError:
            raise ValueError(f"invalid status range: {value!r}") from None

    if not (100 <= low <= 599 and 100 <= high <= 599):
        raise ValueError(f"status range must be within 100-599: {value!r}")
    if low > high:
        raise ValueError(f"status range lower bound exceeds upper bound: {value!r}")
    return low, high


def check_tcp(host: str, port: int, timeout: float = DEFAULT_TIMEOUT) -> None:
    """Attempt a single TCP connection to ``host:port``.

    Args:
        host: Target host name or IP address.
        port: Target TCP port.
        timeout: Per-attempt timeout in seconds.

    Returns:
        ``None`` when the connection succeeds.

    Raises:
        CheckError: If the connection cannot be established.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return None
    except OSError as exc:
        raise CheckError(f"TCP connect to {host}:{port} failed: {exc}") from exc


def check_http(
    url: str,
    status_min: int = 200,
    status_max: int = 399,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Attempt a single HTTP(S) GET request and evaluate the status code.

    Redirects are followed automatically by :mod:`urllib`. A server response
    within ``[status_min, status_max]`` counts as ready; any other status (or a
    transport failure) is treated as not ready.

    Args:
        url: The fully qualified HTTP(S) URL to probe.
        status_min: Lowest accepted status code, inclusive.
        status_max: Highest accepted status code, inclusive.
        timeout: Per-attempt timeout in seconds.

    Returns:
        ``None`` when the response status is within the accepted range.

    Raises:
        CheckError: If the request fails or the status is out of range.
    """
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        # The server answered, but with an error status. Treat it as an
        # observed status so the range check can decide readiness.
        status = exc.code
    except (urllib.error.URLError, OSError) as exc:
        raise CheckError(f"HTTP request to {url} failed: {exc}") from exc

    if status is None:
        raise CheckError(f"HTTP request to {url} returned no status code")
    if not status_min <= status <= status_max:
        raise CheckError(
            f"HTTP {url} returned status {status} (expected {status_min}-{status_max})"
        )
    return None
