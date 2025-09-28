# backend/proxy/handlers.py
import time
import logging
import traceback
from typing import Tuple
from flask import Response, jsonify
from cache.lru_cache import CacheEntry, LRUCache
from .fetcher import fetch_url

logger = logging.getLogger("swiftcache")
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG)

def build_response_from_entry(entry: CacheEntry, cache_hit: bool) -> Response:
    resp = Response(entry.body, status=entry.status)
    for k, v in (entry.headers or {}).items():
        try:
            resp.headers[k] = v
        except Exception:
            pass
    resp.headers["X-Cache-Hit"] = "1" if cache_hit else "0"
    resp.headers["X-Cached"] = "1"
    return resp

def handle_fetch(cache: LRUCache, url: str, fetch_timeout: int = 10) -> Tuple[Response, int]:
    # Basic validation: ensure scheme present
    if not url or not isinstance(url, str):
        return jsonify({"error": "invalid url"}), 400
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"error": "invalid url: scheme missing. Use http:// or https://"}), 400

    # Try cache
    entry = cache.get(url)
    if entry:
        resp = build_response_from_entry(entry, cache_hit=True)
        return resp, resp.status_code

    # Not in cache -> fetch
    try:
        status_code, headers, body = fetch_url(url, timeout=fetch_timeout, stream=False)
    except Exception as e:
        # log full traceback for debugging
        logger.error("Error fetching URL %s: %s", url, e)
        logger.error(traceback.format_exc())
        return jsonify({"error": "upstream fetch failed", "detail": str(e)}), 502

    # Create entry and try to cache
    new_entry = CacheEntry(
        status=status_code,
        headers=headers,
        body=body,
        size=len(body),
        created_at=time.time()
    )
    cached = cache.put(url, new_entry)
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
    return {
        "items": cache.list_cache(),
        "stats": cache.stats()
    }