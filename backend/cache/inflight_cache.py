# backend/cache/inflight_cache.py
import time
from threading import Lock, Event
from typing import Optional, Dict, Tuple

from .lru_cache import LRUCache, CacheEntry

class InflightRequest:
    """Represents a request currently being fetched."""
    def __init__(self):
        self.event = Event()  # waiters block on this
        self.result: Optional[CacheEntry] = None
        self.error: Optional[Exception] = None

class InflightCache:
    """
    A wrapper around LRUCache that also handles "inflight" request coalescing.
    This ensures that if multiple identical requests arrive simultaneously, only one
    request is sent to the origin server.
    """

    def __init__(self, capacity_bytes: int):
        # The actual persistent LRU cache
        self.lru = LRUCache(capacity_bytes=capacity_bytes)
        # A temporary dictionary to track requests currently being fetched
        self.inflight_requests: Dict[str, InflightRequest] = {}
        # A lock to protect access to the inflight_requests dictionary
        self.lock = Lock()
        # A counter for actual fetches made to the origin
        self.origin_fetches = 0

    def fetch_or_wait(self, url: str, fetcher_callable) -> Tuple[Optional[CacheEntry], bool, bool, Optional[Exception]]:
        """
        This is the main entry point. It either gets from cache, waits for an
        inflight request, or performs a new fetch.

        Returns:
            - CacheEntry or None
            - bool: True if this thread performed the origin fetch.
            - bool: True if this thread waited for another thread.
            - Exception or None: If the origin fetch failed.
        """
        # 1. First, check the persistent LRU cache.
        cached_entry = self.lru.get(url)
        if cached_entry:
            return cached_entry, False, False, None

        # 2. If not in cache, check if another thread is already fetching it.
        with self.lock:
            if url in self.inflight_requests:
                # --- WAITER PATH ---
                # Another thread is already fetching this. We wait.
                req = self.inflight_requests[url]
                waited = True
                performed_fetch = False
            else:
                # --- OWNER PATH ---
                # No other thread is fetching it. It's our job now.
                req = InflightRequest()
                self.inflight_requests[url] = req
                waited = False
                performed_fetch = True
                self.origin_fetches += 1

        if waited:
            # This thread waits for the owner thread to finish fetching.
            # The event will be set by the owner, either with a result or an error.
            req.event.wait()
            return req.result, performed_fetch, waited, req.error

        if performed_fetch:
            # This is the "owner" thread. It performs the actual network request.
            try:
                # Call the provided function to fetch from the origin
                status, headers, body = fetcher_callable()
                
                # Create a cache entry from the result
                entry = CacheEntry(
                    status=status,
                    headers=headers,
                    body=body,
                    size=len(body),
                    created_at=time.time()
                )
                
                # Store the successful result for any waiting threads
                req.result = entry
                req.error = None

                # ==============================================================================
                # ### <<< LOGICAL FIX START >>> ###
                # ==============================================================================
                # This was the missing piece. After a successful fetch, we must put the
                # entry into our persistent LRU cache for future requests. We only
                # cache successful responses (e.g., status 200 OK).
                is_success = 200 <= entry.status < 400
                if is_success:
                    print(f"[CACHE] Storing successful response for {url} in LRU cache. Size: {entry.size} bytes.")
                    self.lru.put(url, entry)
                else:
                    print(f"[CACHE] Not caching unsuccessful response for {url} (Status: {entry.status}).")
                # ==============================================================================
                # ### <<< LOGICAL FIX END >>> ###
                # ==============================================================================

            except Exception as e:
                # If the fetch failed, store the error for waiting threads
                req.result = None
                req.error = e
            finally:
                # The fetch is complete (or failed). Remove it from inflight requests
                # and notify all waiting threads by setting the event.
                with self.lock:
                    if url in self.inflight_requests:
                        del self.inflight_requests[url]
                req.event.set()
            
            return req.result, performed_fetch, waited, req.error
        
        # This part should not be reachable
        return None, False, False, Exception("Invalid state in InflightCache")

    def list_cache(self):
        """Pass through to the underlying LRU cache."""
        return self.lru.list_cache()

    def stats(self):
        """Combine stats from LRU and inflight operations."""
        lru_stats = self.lru.stats()
        with self.lock:
            lru_stats["inflight_requests"] = len(self.inflight_requests)
        lru_stats["origin_fetches"] = self.origin_fetches
        return lru_stats
