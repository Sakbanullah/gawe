"""URL validation (SSRF guard).

Rules from SECURITY.md §4: HTTPS only, no credentials, public host only,
every redirect re-validated, bounded timeout/size/redirects.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urlsplit

MAX_REDIRECTS = 5
TIMEOUT_S = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}


class UnsafeUrl(ValueError):
    """URL rejected by the guard. Message never contains credentials."""


Resolver = Callable[[str, int], list[str]]


def _default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def _is_blocked_ip(raw_ip: str) -> bool:
    ip = ipaddress.ip_address(raw_ip.split("%", 1)[0])
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


@dataclass(frozen=True)
class SafeUrl:
    url: str
    host: str
    port: int


def validate_url(url: str, resolver: Resolver | None = None) -> SafeUrl:
    if not isinstance(url, str) or not url.strip():
        raise UnsafeUrl("url is required")
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https":
        raise UnsafeUrl("only https urls are allowed")
    if parts.username or parts.password:
        raise UnsafeUrl("url must not contain credentials")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeUrl("url must contain a host")
    if host in BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise UnsafeUrl("host is not public")
    try:
        port = parts.port or 443
    except ValueError as exc:
        raise UnsafeUrl("invalid port") from exc
    if port not in (443, 8443):
        raise UnsafeUrl("port is not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        addresses = (resolver or _default_resolver)(host, port)
        if not addresses:
            raise UnsafeUrl("host did not resolve")
        for address in addresses:
            if _is_blocked_ip(address):
                raise UnsafeUrl("host resolves to a non-public address")
    else:
        if _is_blocked_ip(str(ip)):
            raise UnsafeUrl("host is a non-public address")
    return SafeUrl(url=url.strip(), host=host, port=port)


def validate_redirect_chain(
    urls: Iterable[str], resolver: Resolver | None = None
) -> list[SafeUrl]:
    chain = [validate_url(url, resolver) for url in urls]
    if len(chain) > MAX_REDIRECTS + 1:
        raise UnsafeUrl("too many redirects")
    return chain
