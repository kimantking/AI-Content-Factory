from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import get_settings

_BLOCKED_SCHEMES = {"file", "gopher", "ftp", "data", "dict", "ldap"}
_ALLOWED_SCHEMES = {"http", "https"}
_METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


class SSRFBlocked(ValueError):
    pass


def _ip_is_dangerous(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_multicast or addr.is_reserved or addr.is_unspecified
        or (isinstance(addr, ipaddress.IPv4Address) and str(addr).startswith("169.254."))
    )


def is_safe_url(url: str, *, extra_allow_hosts: list[str] | None = None) -> tuple[bool, str]:
    s = get_settings()
    if not s.ssrf_enforce:
        return True, "ssrf enforcement disabled"
    try:
        p = urlparse(url)
    except ValueError:
        return False, "unparseable url"
    scheme = (p.scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES or scheme not in _ALLOWED_SCHEMES:
        return False, f"scheme not allowed: {scheme or '(none)'}"
    host = (p.hostname or "").lower()
    if not host:
        return False, "no host"

    allow = set(h.lower() for h in (s.ssrf_allow_hosts or []))
    allow |= set(h.lower() for h in (extra_allow_hosts or []))
    if host in allow:
        return True, "host allowlisted"

    if host in _METADATA_HOSTS or host.endswith(".internal"):
        return False, "metadata/internal host blocked"
    if host in ("localhost", "0.0.0.0", "ip6-localhost"):
        return False, "localhost blocked"

    # resolve and check every A/AAAA record
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, "dns resolution failed"
    for info in infos:
        ip = info[4][0]
        if _ip_is_dangerous(ip):
            return False, f"resolves to blocked address {ip}"
    return True, "ok"


def require_safe_url(url: str, *, extra_allow_hosts: list[str] | None = None) -> str:
    ok, reason = is_safe_url(url, extra_allow_hosts=extra_allow_hosts)
    if not ok:
        raise SSRFBlocked(f"blocked url {url!r}: {reason}")
    return url
