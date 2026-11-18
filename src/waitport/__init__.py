"""waitport - wait for TCP ports and HTTP(S) services to become ready.

A small, dependency-free command line utility that polls one or more targets
until they accept connections (TCP) or return an accepted HTTP status range
(HTTP/HTTPS). It is designed to orchestrate startup order for Docker Compose,
CI pipelines, and shell scripts.
"""

from .checks import CheckError, Target, check_http, check_tcp, parse_target, parse_status_range
from .wait import CheckResult, wait_for_targets

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "Target",
    "CheckError",
    "CheckResult",
    "parse_target",
    "parse_status_range",
    "check_tcp",
    "check_http",
    "wait_for_targets",
]
