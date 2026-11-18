"""Concurrent orchestration for waiting on many targets at once.

:func:`wait_for_targets` runs one independent polling loop per target inside a
bounded thread pool, so a large target list is probed concurrently while the
overall wall-clock deadline is shared across all of them.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .checks import CheckError, Target, check_http, check_tcp

__all__ = ["CheckResult", "wait_for_targets"]


@dataclass
class CheckResult:
    """The outcome of waiting for a single target.

    Attributes:
        target: The original target string.
        ok: ``True`` if the target became ready before the deadline.
        elapsed_ms: Milliseconds spent waiting for this target.
        error: The last error message if ``ok`` is ``False``, else ``None``.
    """

    target: str
    ok: bool
    elapsed_ms: int
    error: Optional[str] = None

    def as_dict(self) -> dict:
        """Return a JSON-serialisable representation of the result."""
        return {
            "target": self.target,
            "ok": self.ok,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
        }


def _attempt(
    target: Target,
    status_min: int,
    status_max: int,
    attempt_timeout: float,
) -> None:
    """Perform one readiness attempt for ``target``."""
    if target.kind == "tcp":
        check_tcp(target.host, target.port, timeout=attempt_timeout)
    else:
        check_http(
            target.url or "",
            status_min=status_min,
            status_max=status_max,
            timeout=attempt_timeout,
        )


def _wait_one(
    target: Target,
    deadline: float,
    interval: float,
    attempt_timeout: float,
    status_min: int,
    status_max: int,
) -> CheckResult:
    """Poll a single target until it is ready or the shared deadline passes."""
    start = time.monotonic()
    last_error: Optional[str] = None

    while True:
        try:
            _attempt(target, status_min, status_max, attempt_timeout)
        except CheckError as exc:
            last_error = str(exc)
        else:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CheckResult(target=target.raw, ok=True, elapsed_ms=elapsed_ms, error=None)

        now = time.monotonic()
        if now >= deadline:
            elapsed_ms = int((now - start) * 1000)
            return CheckResult(
                target=target.raw,
                ok=False,
                elapsed_ms=elapsed_ms,
                error=last_error or "timed out",
            )
        time.sleep(min(interval, max(0.0, deadline - now)))


def wait_for_targets(
    targets: Sequence[Target],
    *,
    timeout: float = 30.0,
    interval: float = 0.5,
    concurrency: int = 8,
    status_min: int = 200,
    status_max: int = 399,
    attempt_timeout: Optional[float] = None,
) -> List[CheckResult]:
    """Wait for every target to become ready, concurrently.

    Args:
        targets: Parsed :class:`Target` objects to wait on.
        timeout: Overall wall-clock budget in seconds shared by all targets.
        interval: Delay between polling attempts for a given target, in seconds.
        concurrency: Maximum number of targets probed simultaneously.
        status_min: Lowest accepted HTTP status code, inclusive.
        status_max: Highest accepted HTTP status code, inclusive.
        attempt_timeout: Per-attempt socket/request timeout in seconds. When
            omitted it defaults to ``max(interval, 0.1)``.

    Returns:
        One :class:`CheckResult` per input target, in the same order.

    Raises:
        ValueError: If ``timeout``, ``interval`` or ``concurrency`` are invalid.
    """
    if timeout <= 0:
        raise ValueError("timeout must be greater than 0")
    if interval <= 0:
        raise ValueError("interval must be greater than 0")
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    if not targets:
        return []

    if attempt_timeout is None:
        attempt_timeout = max(interval, 0.1)

    deadline = time.monotonic() + timeout
    workers = min(concurrency, len(targets))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _wait_one,
                target,
                deadline,
                interval,
                attempt_timeout,
                status_min,
                status_max,
            )
            for target in targets
        ]
        # ``executor.submit`` preserves order in ``futures``; collecting in the
        # same order keeps the output aligned with the caller's target list.
        return [future.result() for future in futures]
