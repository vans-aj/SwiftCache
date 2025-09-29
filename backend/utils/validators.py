# backend/utils/validators.py
"""
Simple validators and blocklist utilities.

Provides:
 - is_allowed(url) -> (bool, reason)
 - get_blocklist(), add_blocklist(domain), remove_blocklist(domain)
 - hostname extraction helper
"""

from urllib.parse import urlparse
from typing import Tuple, List
import threading

# Thread-safe blocklist container
_blocklist_lock = threading.Lock()
# initial blocklist entries (customize)
_blocklist = set([
    "facebook.com",
    "example-bad.com"
])

def _normalize_host(host: str) -> str:
    """Return canonical host (lowercase, strip trailing dot)."""
    if not host:
        return ""
    host = host.lower().rstrip(".")
    return host

def extract_hostname(url: str) -> str:
    """Return hostname from URL or empty string on failure."""
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return ""

def is_blocked_hostname(hostname: str) -> Tuple[bool, str]:
    """
    Check if hostname or its parent domain is in blocklist.
    Returns (True, matching_blocked_item) if blocked, else (False, "").
    """
    if not hostname:
        return True, "empty hostname"
    host = _normalize_host(hostname)
    with _blocklist_lock:
        for bad in _blocklist:
            badn = bad.lower().rstrip(".")
            # match exact or subdomain (endswith .bad)
            if host == badn or host.endswith("." + badn):
                return True, badn
    return False, ""

def is_allowed(url: str) -> Tuple[bool, str]:
    """
    Validate URL and check blocklist.
    Returns (True, "") if allowed, otherwise (False, reason).
    """
    host = extract_hostname(url)
    if not host:
        return False, "invalid or missing hostname"
    blocked, which = is_blocked_hostname(host)
    if blocked:
        return False, f"blocked domain ({which})"
    return True, ""

def get_blocklist() -> List[str]:
    with _blocklist_lock:
        return sorted(list(_blocklist))

def add_blocklist(domain: str) -> bool:
    """Add a domain to blocklist. Returns True if added, False if already present."""
    if not domain:
        return False
    d = domain.lower().rstrip(".")
    with _blocklist_lock:
        if d in _blocklist:
            return False
        _blocklist.add(d)
        return True

def remove_blocklist(domain: str) -> bool:
    """Remove domain from blocklist. Returns True if removed, False if not present."""
    if not domain:
        return False
    d = domain.lower().rstrip(".")
    with _blocklist_lock:
        if d in _blocklist:
            _blocklist.remove(d)
            return True
        return False