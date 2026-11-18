# waitport

> Wait for TCP ports and HTTP(S) services to become ready — one small, dependency-free command.

[![CI](https://github.com/DelmarMG91/waitport/actions/workflows/ci.yml/badge.svg)](https://github.com/DelmarMG91/waitport/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/waitport.svg)](https://pypi.org/project/waitport/)
[![Python versions](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://pypi.org/project/waitport/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`waitport` blocks until every target you give it accepts a TCP connection or
answers an HTTP request with an accepted status code. It is built for the
boring-but-critical gaps in local development, Docker Compose stacks, CI
pipelines, and shell scripts: the database container is "up" before it is
accepting connections, the API process exists before it can serve `/health`.

## Features

- **One command, many targets** — all targets must be ready before `waitport`
  exits successfully.
- **TCP and HTTP(S)** — plain `host:port`, `tcp://host:port`, `http://` and
  `https://` targets in the same invocation.
- **Configurable HTTP acceptance** — accept any status range (default
  `200-399`) and follow redirects automatically.
- **Concurrent polling** — up to `--concurrency` targets are probed in
  parallel, each on its own `--interval` cadence.
- **Automation friendly** — `--json` emits one structured record per target;
  `--quiet` prints a single summary line.
- **Clear exit codes** — `0` ready, `1` timeout, `2` usage error.
- **Zero runtime dependencies** — Python 3.9+ standard library only.

## Install

From PyPI:

```console
$ pip install waitport
```

From a checkout, including the test dependencies:

```console
$ pip install -e ".[dev]"
```

## Quick Start

### Docker Compose

Run `waitport` as a one-shot gate before an application or migration step:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: example

  migrate:
    image: python:3.12-slim
    depends_on:
      - db
    command: >
      sh -c "pip install --quiet waitport &&
             waitport db:5432 --timeout 60 --interval 1"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/postgres

  api:
    build: .
    depends_on:
      migrate:
        condition: service_completed_successfully
    ports:
      - "8080:8080"
```

`waitport` polls `db:5432` until PostgreSQL accepts connections, then exits `0`
and lets Compose start `api`.

### CI

Gate integration tests on the services started earlier in the job:

```yaml
- name: Wait for services
  run: |
    pip install waitport
    waitport localhost:5432 http://localhost:8080/health \
      --timeout 60 --interval 1 --json
```

A non-zero exit fails the step, so the test command that follows never runs
against a half-started stack.

### Shell scripts

```bash
#!/usr/bin/env bash
set -euo pipefail

waitport tcp://127.0.0.1:6379 http://127.0.0.1:8000/healthz --timeout 30
exec ./run-tests.sh
```

## Usage

```console
$ waitport db:5432 http://localhost:8080/health --timeout 20
[ok]   db:5432  (12 ms)
[ok]   http://localhost:8080/health  (243 ms)
all 2 target(s) ready
```

When a target does not become ready in time, the failing target and the last
observed error are printed and the exit code is `1`:

```console
$ waitport db:5432 http://localhost:8080/health --timeout 10
[ok]   db:5432  (8 ms)
[fail] http://localhost:8080/health  HTTP request to http://localhost:8080/health failed: <urlopen error [Errno 111] Connection refused>
1 of 2 target(s) not ready
```

Machine-readable output with `--json`:

```console
$ waitport db:5432 http://localhost:8080/health --json --timeout 20
[{"target": "db:5432", "ok": true, "elapsed_ms": 9, "error": null}, {"target": "http://localhost:8080/health", "ok": true, "elapsed_ms": 241, "error": null}]
```

Quiet mode prints only the final summary:

```console
$ waitport db:5432 --quiet
ready: 1 target(s) in 11 ms
```

## Target syntax

| Form | Example | Check performed |
| --- | --- | --- |
| `host:port` | `db:5432` | TCP connect to `db` on port `5432` |
| `tcp://host:port` | `tcp://cache:6379` | TCP connect to `cache` on port `6379` |
| `http://url` | `http://localhost:8080/health` | HTTP GET, redirects followed, status checked |
| `https://url` | `https://example.com/status` | HTTPS GET, redirects followed, status checked |

Notes:

- A bare `host:port` is treated as TCP. Use an explicit `http://` or `https://`
  prefix for HTTP checks.
- IPv6 literals use brackets: `[::1]:8080`.
- A URL without an explicit port defaults to `80` for `http://` and `443` for
  `https://`.
- Multiple targets may be mixed freely on one command line.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `TARGET...` | *(required)* | One or more targets to wait for. |
| `--timeout SECONDS` | `30` | Overall wall-clock budget shared by all targets. |
| `--interval SECONDS` | `0.5` | Delay between polling attempts for each target. |
| `--concurrency N` | `8` | Maximum number of targets checked in parallel. |
| `--http-status RANGE` | `200-399` | Accepted HTTP status range, e.g. `200-399` or `204`. |
| `--json` | off | Print a JSON array of `{target, ok, elapsed_ms, error}` records. |
| `--quiet` | off | Suppress per-target lines; print only the final summary. |
| `--version` | — | Print the version and exit. |
| `--help` | — | Print help and exit. |

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Every target became ready before the timeout. |
| `1` | At least one target was not ready when the timeout expired. |
| `2` | Invalid command line usage (bad target, bad option value, …). |

## Development

The project uses a `src/` layout and only the standard library at runtime.

```console
$ python -m venv .venv
$ . .venv/bin/activate          # Windows: .venv\Scripts\activate
$ pip install -e ".[dev]"
$ python -m pytest -q
```

The test suite uses ephemeral localhost sockets and a local `http.server`
instance; it never touches external networks.

## Contributing

Issues and pull requests are welcome. Please keep changes focused, add or update
tests for behaviour changes, and make sure `python -m pytest -q` passes before
opening a pull request. By contributing you agree that your changes are released
under the MIT license.

## License

Released under the MIT License. See [LICENSE](LICENSE) for details.
