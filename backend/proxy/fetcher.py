# backend/proxy/fetcher.py
"""
Simple fetcher module.
- performs network fetch using requests
- filters hop-by-hop headers
- returns a small object suitable for caching (status, headers, body)
"""

import requests
from typing import Dict, Tuple
from requests.exceptions import RequestException

# basic hop-by-hop headers we don't forward to client/cache
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade"
}

def filter_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Return a clean headers dict removing hop-by-hop headers and sensitive ones."""
    out = {}
    for k, v in headers.items():
        if k.lower() in HOP_BY_HOP:
            continue
        # skip set-cookie for simplicity (optional)
        if k.lower() == "set-cookie":
            continue
        out[k] = v
    return out

def fetch_url(url: str, timeout: int = 10, stream: bool = False) -> Tuple[int, Dict[str,str], bytes]:
    """
    Fetch the given URL and return (status_code, filtered_headers, body_bytes).
    Raises RequestException on errors.
    """
    try:
        # Use stream=False to get full content; for very large responses you may want stream=True
        r = requests.get(url, timeout=timeout, stream=stream)
        # read content (if stream True you'd handle differently)
        body = r.content if not stream else b""
        headers = filter_headers(r.headers)
        return r.status_code, headers, body
    except RequestException as e:
        # bubble up exception to caller so handler can return proper error
        raise