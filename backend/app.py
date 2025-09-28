# backend/app.py (only the relevant parts shown)
from flask import Flask, request
from flask_cors import CORS
import time

from cache.lru_cache import LRUCache
from proxy.handlers import handle_fetch, handle_list_cache

app = Flask(__name__)
CORS(app)

CACHE_CAPACITY_BYTES = 5 * 1024 * 1024
cache = LRUCache(capacity_bytes=CACHE_CAPACITY_BYTES)

@app.route("/fetch", methods=["POST"])
def fetch_route():
    data = request.get_json() or {}
    url = data.get("url")
    resp, code = handle_fetch(cache, url)
    return resp, code

@app.route("/cache", methods=["GET"])
def cache_route():
    return handle_list_cache(cache)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)