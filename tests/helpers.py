"""Small local fixtures shared by the waitport test-suite.

Everything here binds to ``127.0.0.1`` on an ephemeral port so the tests never
touch external networks and can run in parallel with other test suites.
"""

from __future__ import annotations

import contextlib
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator


@contextlib.contextmanager
def open_tcp_port() -> Iterator[int]:
    """Yield a port with a real listening socket bound to localhost."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


def free_port() -> int:
    """Return a port that was just released and is very likely unused."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


class _TestHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler with deterministic paths for the tests."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.startswith("/missing"):
            status = 404
        elif self.path.startswith("/error"):
            status = 500
        elif self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        else:
            status = 200

        body = b"ok"
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Silence per-request logging during tests."""


@contextlib.contextmanager
def http_server() -> Iterator[str]:
    """Yield the base URL of a local HTTP server running on an ephemeral port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TestHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
