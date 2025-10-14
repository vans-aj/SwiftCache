# backend/cache/lru_cache.py
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Optional, Dict, Any

@dataclass
class CacheEntry:
    status: int
    headers: Dict[str, str]
    body: bytes
    size: int
    created_at: float

    def to_dict(self):
        return {
            "status": self.status,
            "size": self.size,
            "created_at": self.created_at
        }

class LRUCache:
    def __init__(self, capacity_bytes: int):
        self.capacity = capacity_bytes
        self.current_usage = 0
        self.map = OrderedDict()  # URL → CacheEntry
        self.lock = Lock()
        self.hits = 0
        self.misses = 0

    def _evict_if_needed(self, needed_bytes: int):
        """Evict least recently used items until enough space is free."""
        while self.current_usage + needed_bytes > self.capacity and self.map:
            _, evicted = self.map.popitem(last=True)  # pop LRU
            self.current_usage -= evicted.size

    def get(self, url: str) -> Optional[CacheEntry]:
        """Return cache entry if exists; update MRU position."""
        with self.lock:
            entry = self.map.get(url)
            if entry:
                self.map.move_to_end(url, last=False)  # mark as MRU
                self.hits += 1
                return entry
            else:
                self.misses += 1
                return None

    def put(self, url: str, entry: CacheEntry) -> bool:
        """Insert into cache, evicting old entries if needed."""
        if entry.size > self.capacity:
            return False  # too big, skip caching

        with self.lock:
            # Remove old entry if exists
            old = self.map.pop(url, None)
            if old:
                self.current_usage -= old.size

            self._evict_if_needed(entry.size)
            self.map[url] = entry
            self.map.move_to_end(url, last=False)  # MRU
            self.current_usage += entry.size
            return True

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self.lock:
            return {
                "capacity_bytes": self.capacity,
                "current_usage_bytes": self.current_usage,
                "items": len(self.map),
                "hits": self.hits,
                "misses": self.misses
            }

    def list_cache(self):
        """Return list of cached items for dashboard."""
        with self.lock:
            return [
                {"url": k, "size": v.size, "created_at": v.created_at}
                for k, v in self.map.items()
            ]
        