"""Safety checks for user-provided integration URLs.

The rules are intentionally configuration-driven to support future providers,
multiple instances, and internal/private deployments.
"""

from __future__ import annotations

import ipaddress
import os
from fnmatch import fnmatch
from urllib.parse import urlsplit


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _allowed_schemes() -> set[str]:
    raw = os.getenv("INTEGRATION_ALLOWED_URL_SCHEMES", "https")
    schemes = {s.strip().lower() for s in raw.split(",") if s.strip()}
    return schemes or {"https"}


def _allowed_host_patterns() -> list[str]:
    raw = os.getenv("INTEGRATION_ALLOWED_HOST_PATTERNS", "")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def _is_blocked_ip(ip_text: str, allow_private_ips: bool) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False

    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    if not allow_private_ips and (ip.is_private or ip.is_reserved):
        return True
    return False


def validate_and_normalize_instance_url(raw_url: str) -> str:
    """Validate integration base URL and return normalized value.

    Environment controls:
    - INTEGRATION_ALLOWED_URL_SCHEMES: comma-separated schemes, default: https
    - INTEGRATION_ALLOWED_HOST_PATTERNS: optional host globs (e.g. *.atlassian.net)
    - INTEGRATION_ALLOW_PRIVATE_IPS: allow RFC1918/private IP literals, default: true
    - INTEGRATION_ALLOW_LOCALHOST: allow localhost/loopback hostnames, default: false
    """
    candidate = (raw_url or "").strip()
    if not candidate:
        raise ValueError("instance_url is empty")

    parsed = urlsplit(candidate)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("instance_url must be an absolute URL")

    scheme = parsed.scheme.lower()
    if scheme not in _allowed_schemes():
        raise ValueError(f"URL scheme '{scheme}' is not allowed")

    if parsed.username or parsed.password:
        raise ValueError("Credentials in instance_url are not allowed")

    if parsed.query or parsed.fragment:
        raise ValueError(
            "Query parameters and fragments are not allowed in instance_url"
        )

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("instance_url host is missing")

    allow_localhost = _env_flag("INTEGRATION_ALLOW_LOCALHOST", False)
    if not allow_localhost and host in {"localhost", "localhost.localdomain"}:
        raise ValueError("localhost is not allowed for integration instance_url")

    allow_private_ips = _env_flag("INTEGRATION_ALLOW_PRIVATE_IPS", True)
    if _is_blocked_ip(host, allow_private_ips):
        raise ValueError("This host is not allowed for integration instance_url")

    patterns = _allowed_host_patterns()
    if patterns and not any(fnmatch(host, p) for p in patterns):
        raise ValueError("Host is not in INTEGRATION_ALLOWED_HOST_PATTERNS")

    normalized = f"{scheme}://{parsed.netloc}{parsed.path or ''}"
    return normalized.rstrip("/")
