# backend/cache/inflight_cache.py
import time
import logging
from threading import Lock, Event
from typing import Callable, Dict, Any, Tuple, Optional

from .lru_cache import LRUCache, CacheEntry

logger = logging.getLogger("swiftcache.inflight")
if not logger.handlers:
    logging.basicConfig(level=logging.DEBUG)

class InflightCache:
    def __init__(self, capacity_bytes: int):
        self._cache = LRUCache(capacity_bytes=capacity_bytes)
        # inflight: url -> {"event": Event, "entry": Optional[CacheEntry], "error": Optional[Exception]}
        self._inflight: Dict[str, Dict[str, Any]] = {}
        self._inflight_lock = Lock()
        self._origin_fetches = 0
        self._origin_fetches_lock = Lock()

    # passthroughs
    def stats(self):
        s = self._cache.stats()
        with self._origin_fetches_lock:
            s["origin_fetches"] = self._origin_fetches
        return s

    def list_cache(self):
        return self._cache.list_cache()

    def put(self, url: str, entry: CacheEntry) -> bool:
        return self._cache.put(url, entry)

    def get(self, url: str) -> Optional[CacheEntry]:
        return self._cache.get(url)

    # core inflight logic
    def fetch_or_wait(self, url: str, fetcher_callable: Callable[[], Tuple[int, Dict[str,str], bytes]], max_wait: Optional[float] = None) -> Tuple[Optional[CacheEntry], bool, bool, Optional[Exception]]:
        """
        Return (entry_or_none, performed_fetch(bool), waited(bool), error_or_none)
        """
        # 1) Fast path: memory cache
        entry = self._cache.get(url)
        if entry:
            logger.debug("Cache hit (fast) for %s", url)
            return entry, False, False, None

        # 2) Need inflight coordination
        with self._inflight_lock:
            rec = self._inflight.get(url)
            if rec:
                # someone else is fetching
                event = rec["event"]
                logger.debug("Found inflight for %s, will wait", url)
                owner = False
            else:
                # become owner
                event = Event()
                self._inflight[url] = {"event": event, "entry": None, "error": None}
                logger.debug("No inflight for %s -> becoming owner", url)
                owner = True

        if not owner:
            # wait until owner sets event (or timeout)
            waited = True
            event.wait(timeout=max_wait)
            # after wait, read result from inflight record if present, else check cache
            with self._inflight_lock:
                rec_after = self._inflight.get(url)
            if rec_after:
                # owner still present or just finished but record kept until owner cleans up
                entry = rec_after.get("entry")
                err = rec_after.get("error")
            else:
                # owner cleaned up; try cache as backup
                entry = self._cache.get(url)
                err = None
            logger.debug("Waiter for %s resumed: entry=%s err=%s", url, bool(entry), bool(err))
            return entry, False, True, err

        # Owner path: perform the fetch
        performed_fetch = True
        waited = False
        err = None
        entry = None
        try:
            logger.debug("Owner performing origin fetch for %s", url)
            status, headers, body = fetcher_callable()
            entry_obj = CacheEntry(status=status, headers=headers, body=body, size=len(body), created_at=time.time())
            put_ok = self._cache.put(url, entry_obj)
            # increment origin counter
            with self._origin_fetches_lock:
                self._origin_fetches += 1
            entry = entry_obj if put_ok else entry_obj
            logger.debug("Owner fetch complete for %s (cached=%s)", url, bool(put_ok))
        except Exception as e:
            err = e
            logger.exception("Owner fetch error for %s: %s", url, e)
        finally:
            # notify waiters and remove inflight record
            with self._inflight_lock:
                rec2 = self._inflight.get(url)
                if rec2:
                    rec2["entry"] = entry
                    rec2["error"] = err
                    try:
                        rec2["event"].set()
                    except Exception:
                        logger.debug("Failed to set event for %s", url)
                    # remove from inflight so later readers check cache directly
                    try:
                        del self._inflight[url]
                    except KeyError:
                        pass
            logger.debug("Owner cleanup done for %s", url)

        return entry, performed_fetch, waited, err 