"""Low-level TCP/TLS tuning for the network engine.

Controls socket options, TCP_NODELAY, keep-alive probes, and buffer sizes
for optimal scraping performance.
"""

from __future__ import annotations

import socket
import struct

import structlog

logger = structlog.get_logger(__name__)


def configure_socket(sock: socket.socket, tcp_keepalive_seconds: int = 60) -> None:
    """Apply performance-oriented socket options."""
    # Disable Nagle's algorithm — reduce latency for small packets (HTTP headers)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # Enable TCP keep-alive to detect dead connections
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    # Platform-specific keep-alive tuning
    if hasattr(socket, "TCP_KEEPIDLE"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, tcp_keepalive_seconds)
    elif hasattr(socket, "TCP_KEEPALIVE"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, tcp_keepalive_seconds)

    if hasattr(socket, "TCP_KEEPINTVL"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)  # 10s between probes

    if hasattr(socket, "TCP_KEEPCNT"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)  # 3 probes before dead

    # Increase receive buffer for large HTML responses
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)  # 256KB
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 128 * 1024)  # 128KB


def set_tcp_fast_open(sock: socket.socket) -> bool:
    """Enable TCP Fast Open (TFO) if supported by the platform.

    TFO allows data to be sent during the TCP handshake, saving 1 RTT.
    Returns True if enabled successfully.
    """
    try:
        # Linux: TCP_FASTOPEN = 23, value = 1
        sock.setsockopt(socket.IPPROTO_TCP, 23, 1)
        return True
    except (OSError, AttributeError):
        return False


def set_reuse_port(sock: socket.socket) -> bool:
    """Enable SO_REUSEPORT for better load distribution across workers."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # type: ignore[attr-defined]
        return True
    except (OSError, AttributeError):
        return False


def build_http2_settings_frame(
    header_table_size: int = 65536,
    max_concurrent_streams: int = 1000,
    initial_window_size: int = 6291456,  # 6MB
    max_frame_size: int = 16384,
) -> bytes:
    """Build a raw HTTP/2 SETTINGS frame for connection preface.

    Custom settings help mimic real browser HTTP/2 behavior.
    """
    settings = [
        (0x1, header_table_size),
        (0x3, max_concurrent_streams),
        (0x4, initial_window_size),
        (0x5, max_frame_size),
    ]
    payload = b"".join(struct.pack("!HI", k, v) for k, v in settings)
    frame_header = struct.pack("!HBB", len(settings) * 6, 0x04, 0x00)
    return frame_header + payload
