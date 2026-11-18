"""Command line interface for waitport."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Sequence

from . import __version__
from .checks import Target, parse_status_range, parse_target
from .wait import CheckResult, wait_for_targets

__all__ = ["build_parser", "format_results", "main"]

_EXIT_READY = 0
_EXIT_TIMEOUT = 1
_EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``waitport`` command."""
    parser = argparse.ArgumentParser(
        prog="waitport",
        description=(
            "Wait until TCP ports and HTTP(S) endpoints are ready. "
            "Every supplied target must become ready before the command exits successfully."
        ),
        epilog=(
            "Exit codes: 0 = all targets ready; 1 = at least one target was not ready "
            "before the timeout; 2 = invalid command line usage."
        ),
    )
    parser.add_argument(
        "targets",
        metavar="TARGET",
        nargs="+",
        help=(
            "Targets to wait for: host:port, tcp://host:port, http://url or https://url. "
            "Multiple targets may be supplied."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="Overall wait budget in seconds (default: 30).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        metavar="SECONDS",
        help="Delay between polling attempts per target (default: 0.5).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        metavar="N",
        help="Maximum number of targets checked in parallel (default: 8).",
    )
    parser.add_argument(
        "--http-status",
        default="200-399",
        metavar="RANGE",
        help="Accepted HTTP status range, e.g. 200-399 or 200 (default: 200-399).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON array of per-target results instead of human-readable lines.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-target lines and print only the final summary.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the program version and exit.",
    )
    return parser


def format_results(results: Sequence[CheckResult], as_json: bool, quiet: bool) -> str:
    """Render results for display.

    Args:
        results: Results returned by :func:`waitport.wait.wait_for_targets`.
        as_json: When ``True``, render a JSON array.
        quiet: When ``True``, render only the final summary line.

    Returns:
        The text to print, without a trailing newline.
    """
    all_ok = all(result.ok for result in results)
    if as_json:
        return json.dumps([result.as_dict() for result in results], ensure_ascii=False)
    if quiet:
        if all_ok:
            slowest = max((result.elapsed_ms for result in results), default=0)
            return f"ready: {len(results)} target(s) in {slowest} ms"
        failed = sum(1 for result in results if not result.ok)
        return f"not ready: {failed} of {len(results)} target(s)"
    lines: List[str] = []
    for result in results:
        if result.ok:
            lines.append(f"[ok]   {result.target}  ({result.elapsed_ms} ms)")
        else:
            lines.append(f"[fail] {result.target}  {result.error}")
    if all_ok:
        lines.append(f"all {len(results)} target(s) ready")
    else:
        failed = sum(1 for result in results if not result.ok)
        lines.append(f"{failed} of {len(results)} target(s) not ready")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the ``waitport`` command.

    Args:
        argv: Optional argument vector, defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: 0 when every target is ready, 1 on timeout,
        and 2 for invalid usage.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        targets: List[Target] = [parse_target(value) for value in args.targets]
    except ValueError as exc:
        print(f"waitport: error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        status_min, status_max = parse_status_range(args.http_status)
    except ValueError as exc:
        print(f"waitport: error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        results = wait_for_targets(
            targets,
            timeout=args.timeout,
            interval=args.interval,
            concurrency=args.concurrency,
            status_min=status_min,
            status_max=status_max,
        )
    except ValueError as exc:
        print(f"waitport: error: {exc}", file=sys.stderr)
        return _EXIT_USAGE
    except KeyboardInterrupt:
        print("waitport: interrupted", file=sys.stderr)
        return 130

    output = format_results(results, as_json=args.json, quiet=args.quiet)
    if args.json or args.quiet:
        print(output)
    else:
        all_ok = all(result.ok for result in results)
        for result in results:
            if result.ok:
                print(f"[ok]   {result.target}  ({result.elapsed_ms} ms)")
            else:
                print(f"[fail] {result.target}  {result.error}", file=sys.stderr)
        if all_ok:
            print(f"all {len(results)} target(s) ready")
        else:
            failed = sum(1 for result in results if not result.ok)
            print(f"{failed} of {len(results)} target(s) not ready", file=sys.stderr)

    return _EXIT_READY if all(result.ok for result in results) else _EXIT_TIMEOUT


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    raise SystemExit(main())
