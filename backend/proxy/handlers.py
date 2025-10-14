# backend/proxy/handlers.py
import logging
import traceback
from flask import jsonify

from .fetcher import fetch_url

# Configure logging
logger = logging.getLogger("swiftcache")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

def handle_fetch(cache, url: str, fetch_timeout: int = 10):
    """
    This function is now the target for the ThreadPoolExecutor.
    It performs the entire fetch-and-cache logic for a single URL.
    It no longer returns a Flask Response, as it's a background task.
    """
    print(f"[HANDLE_FETCH] Worker thread starting for {url}. Using cache ID: {id(cache)}")

    # Define the actual network fetching function that will be passed to the cache logic.
    def _do_fetch():
        print(f"[FETCHING] No cache hit for {url}. Making a real network request.")
        return fetch_url(url, timeout=fetch_timeout, stream=False)

    try:
        # This is the most important call. It handles checking the cache,
        # waiting if another thread is already fetching, or performing the fetch itself.
        # The result (entry) will be put into the LRU cache from within this method if the fetch is successful.
        entry, performed_fetch, waited, error = cache.fetch_or_wait(url, fetcher_callable=_do_fetch)

        if error:
            logger.error(f"Upstream fetch failed for {url}: {error}")
        elif entry:
            was_hit = not performed_fetch and not waited
            if was_hit:
                logger.info(f"Cache HIT for {url}")
            else:
                logger.info(f"Cache MISS for {url}. Fetched and stored in cache.")
        else:
             logger.error(f"handle_fetch completed for {url} but received no entry and no error.")

    except Exception as e:
        logger.error(f"Critical error in handle_fetch for {url}: {e}")
        logger.error(traceback.format_exc())


def handle_list_cache(cache):
    """
    A simple helper that returns the cache's current state and stats.
    This is called by the /cache API endpoint.
    """
    return {
        "items": cache.list_cache(),
        "stats": cache.stats()
    }