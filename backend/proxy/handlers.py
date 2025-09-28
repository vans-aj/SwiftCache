# backend/proxy/handlers.py
"""
Handlers that implement the main proxy logic using the LRU cache and fetcher.
These functions are independent of Flask so they are easy to test.
"""

import time
from typing import Tuple, Optional
from flask import Response, jsonify
from cache.lru_cache import CacheEntry, LRUCache
from .fetcher import fetch_url


def build_response_from_entry(entry: CacheEntry, cache_hit: bool) -> Response:
    """Create a Flask Response from a CacheEntry."""
    resp = Response(entry.body, status=entry.status)
    # copy useful headers (entry.headers is already filtered by fetcher)
    for k, v in (entry.headers or {}).items():
        try:
            resp.headers[k] = v
        except Exception:
            pass
    resp.headers["X-Cache-Hit"] = "1" if cache_hit else "0"
    resp.headers["X-Cached"] = "1"
    return resp


def handle_fetch(cache: LRUCache, url: str, fetch_timeout: int = 10) -> Tuple[Response, int]:
    """
    Main logic for /fetch:
     - Try cache.get(url) -> if present, return cached response.
     - Else fetch via fetcher.fetch_url, create CacheEntry and cache.put.
     - Return Response object and HTTP status code to the Flask route.
    """
    # 1) Validate url (simple minimal check)
    if not url or not isinstance(url, str):
        return jsonify({"error": "invalid url"}), 400

    # 2) Try cache
    entry = cache.get(url)
    if entry:
        # cache.get already updates hits/misses and MRU positioning
        resp = build_response_from_entry(entry, cache_hit=True)
        return resp, resp.status_code

    # 3) Not in cache -> fetch from origin
    try:
        status_code, headers, body = fetch_url(url, timeout=fetch_timeout, stream=False)
    except Exception as e:
        # network or timeout error
        return jsonify({"error": str(e)}), 502

    # 4) Build CacheEntry and attempt to put into cache
    new_entry = CacheEntry(
        status=status_code,
        headers=headers,
        body=body,
        size=len(body),
        created_at=time.time()
    )
    cached = cache.put(url, new_entry)  # may return False if item too big
    # 5) Build response to return to client
    resp = Response(body, status=status_code)
    for k, v in headers.items():
        try:
            resp.headers[k] = v
        except Exception:
            pass
    resp.headers["X-Cache-Hit"] = "0"
    resp.headers["X-Cached"] = "1" if cached else "0"
    return resp, status_code


def handle_list_cache(cache: LRUCache):
    """Return a JSON-serializable view of cache items and stats."""
    return {
        "items": cache.list_cache(),
        "stats": cache.stats()
    }