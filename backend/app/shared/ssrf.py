"""Shared SSRF guard — textual + resolution-based private-network blocking.

The old per-module prefix checks ("127.", "10.", "172.16.") missed the rest of
the 172.16/12 range, CGNAT, IPv6 ULA/link-local, and non-dotted hosts that
resolve privately (decimal `2130706433`, `0x7f.0.0.1`). This guard resolves the
hostname and judges the actual IPs. TOCTOU DNS-rebinding remains theoretically
possible (check-then-fetch); the fetch layer re-checks per request.

Not async itself: resolution is blocking, so callers on the event loop use
`aassert_public_host`.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # carrier-grade NAT — not "private" in stdlib


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_reserved or addr.is_multicast or addr.is_unspecified
        or (addr.version == 4 and addr in _CGNAT)
    )


def assert_public_host(url: str) -> str:
    """Raise ValueError unless every address `url` resolves to is public."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("url must be http(s) with a host")
    host = parsed.hostname.lower().rstrip(".")
    literal = None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        pass
    if literal is not None:
        if _is_blocked_ip(str(literal)):
            raise ValueError("blocked host (private network range)")
        return host
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise ValueError(f"cannot resolve host {host!r}")
    for info in infos:
        ip = info[4][0]
        try:
            blocked = _is_blocked_ip(ip)
        except ValueError:
            continue  # unparseable resolver answer — ignore that record
        if blocked:
            raise ValueError("blocked host (private network range)")
    return host


async def aassert_public_host(url: str) -> str:
    """Resolution-based SSRF check, off the event loop."""
    return await asyncio.to_thread(assert_public_host, url)
