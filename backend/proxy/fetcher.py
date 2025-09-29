# backend/proxy/fetcher.py
import requests
from typing import Dict, Tuple
from requests.exceptions import RequestException

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade"
}

def filter_headers(headers: Dict[str, str]) -> Dict[str, str]:
    out = {}
    for k, v in headers.items():
        if k.lower() in HOP_BY_HOP:
            continue
        if k.lower() == "set-cookie":
            continue
        out[k] = v
    return out

def fetch_url(url: str, timeout: int = 10, stream: bool = False) -> Tuple[int, Dict[str,str], bytes]:
    """
    Fetch the given URL and return (status_code, filtered_headers, body_bytes).
    Raises RequestException on network errors with a clear message.
    """
    headers = {
        # mimic a common desktop browser so many servers accept the request
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    try:
        r = requests.get(url, headers=headers, timeout=timeout, stream=stream)
        body = r.content if not stream else b""
        headers = filter_headers(r.headers)
        return r.status_code, headers, body
    except RequestException as e:
        # raise with a clearer message for handlers/logs
        raise RequestException(f"requests error for {url}: {e}")