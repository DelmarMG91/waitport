# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-01

### Added

- `waitport` CLI with support for `host:port`, `tcp://host:port`, `http://url`
  and `https://url` targets.
- Concurrent TCP and HTTP(S) readiness checks with configurable timeout,
  polling interval, concurrency, and accepted HTTP status range.
- `--json` structured output and `--quiet` summary mode.
- Deterministic exit codes: `0` ready, `1` timeout, `2` usage error.
- Full pytest suite covering parsing, TCP/HTTP checks, the concurrent wait
  loop, and CLI output modes.

[Unreleased]: https://github.com/DelmarMG91/waitport/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DelmarMG91/waitport/releases/tag/v0.1.0
