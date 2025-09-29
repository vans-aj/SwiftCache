# backend/proxy/handlers.py
import time
import logging
import traceback
from typing import Tuple, Optional, Dict
from flask import Response, jsonify
from cache.lru_cache import CacheEntry          # CacheEntry dataclass retained in lru_cache
from .fetcher import fetch_url

# import validators
from utils.validators import is_allowed, extract_hostname

logger = logging.getLogger("swiftcache")
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG)


def build_response_from_entry(entry: CacheEntry, cache_hit: bool, performed_fetch: bool, waited: bool) -> Response:
    """
    Build a Flask Response from a CacheEntry and set helpful headers for instrumentation.
    """
    resp = Response(entry.body, status=entry.status)
    for k, v in (entry.headers or {}).items():
        try:
            resp.headers[k] = v
        except Exception:
            pass
    resp.headers["X-Cache-Hit"] = "1" if cache_hit else "0"
    resp.headers["X-Performed-Fetch"] = "1" if performed_fetch else "0"
    resp.headers["X-Waited"] = "1" if waited else "0"
    resp.headers["X-Cached"] = "1"
    return resp


def handle_fetch(cache, url: str, fetch_timeout: int = 10) -> Tuple[Response, int]:
    """
    Main logic for /fetch using inflight coalescing:
    - cache.fetch_or_wait(url, fetcher_callable) will ensure only one origin fetch occurs.
    - fetcher_callable must be a zero-arg callable returning (status, headers, body).
    """

    # Basic validation: ensure scheme present
    if not url or not isinstance(url, str):
        return jsonify({"error": "invalid url"}), 400
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"error": "invalid url: scheme missing. Use http:// or https://"}), 400

    # Access control: blocklist check
    allowed, reason = is_allowed(url)
    if not allowed:
        logger.info("Blocked request to %s: %s", extract_hostname(url), reason)
        return jsonify({"error": "forbidden", "detail": reason}), 403

    # Define the fetcher callable (will be executed only by the owner thread)
    def _do_fetch():
        # fetch_url returns (status_code, headers_dict, body_bytes)
        return fetch_url(url, timeout=fetch_timeout, stream=False)

    # Use the inflight wrapper API. The wrapper returns:
    # (entry_or_none, performed_fetch:bool, waited:bool, error_or_none)
    try:
        entry, performed_fetch, waited, error = cache.fetch_or_wait(url, fetcher_callable=_do_fetch)
    except Exception as e:
        # Defensive: if fetch_or_wait itself raises
        logger.error("Unexpected error in fetch_or_wait for %s: %s", url, e)
        logger.error(traceback.format_exc())
        return jsonify({"error": "internal server error", "detail": str(e)}), 500

    if error:
        # upstream fetch failed (owner encountered exception)
        logger.error("Upstream fetch failed for %s: %s", url, error)
        return jsonify({"error": "upstream fetch failed", "detail": str(error)}), 502

    if entry:
        resp = Response(entry.body, status=entry.status)
        for k, v in (entry.headers or {}).items():
            try:
                resp.headers[k] = v
            except Exception:
                pass

        # Decide whether this response was a memory hit or was fetched now
        cache_hit = (not performed_fetch and not waited)

        # Only mark as "cached" if entry.status is a successful status (2xx or maybe 3xx)
        is_success = 200 <= entry.status < 400
        resp.headers["X-Cache-Hit"] = "1" if cache_hit else "0"
        resp.headers["X-Performed-Fetch"] = "1" if performed_fetch else "0"
        resp.headers["X-Waited"] = "1" if waited else "0"
        resp.headers["X-Cached"] = "1" if is_success else "0"
        return resp, entry.status

    # no entry and no error — unexpected
    logger.error("fetch_or_wait returned no entry and no error for %s", url)
    return jsonify({"error": "upstream fetch failed", "detail": "no entry produced"}), 502


def handle_list_cache(cache):
    """
    Return JSON-serializable cache listing and stats.
    Works with either LRUCache or InflightCache (which exposes list_cache() and stats()).
    """
    return {
        "items": cache.list_cache(),
        "stats": cache.stats()
    }