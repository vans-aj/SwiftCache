# backend/app.py
from flask import Flask, request, jsonify, send_from_directory
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask_cors import CORS
import time
import os

from cache.lru_cache import LRUCache
from cache.inflight_cache import InflightCache
from proxy.handlers import handle_fetch, handle_list_cache
from utils.validators import get_blocklist, add_blocklist, remove_blocklist

app = Flask(__name__)
CORS(app)

CACHE_CAPACITY_BYTES = 5 * 1024 * 1024
cache = InflightCache(capacity_bytes=CACHE_CAPACITY_BYTES)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "name": "SwiftCache"})

@app.route("/fetch", methods=["POST"])
def fetch_route():
    data = request.get_json() or {}
    url = data.get("url")
    resp, code = handle_fetch(cache, url)
    return resp, code

@app.route("/cache", methods=["GET"])
def cache_route():
    return handle_list_cache(cache)

@app.route("/admin/blocklist", methods=["GET", "POST"])
def admin_blocklist_get_post():
    if request.method == "GET":
        return jsonify({"blocklist": get_blocklist()})
    data = request.get_json() or {}
    domain = data.get("domain")
    if not domain:
        return jsonify({"error": "missing domain"}), 400
    added = add_blocklist(domain)
    return jsonify({"added": added, "domain": domain})

@app.route("/admin/blocklist", methods=["DELETE"])
def admin_remove_block():
    data = request.get_json() or {}
    domain = data.get("domain")
    if not domain:
        return jsonify({"error": "missing domain"}), 400
    removed = remove_blocklist(domain)
    return jsonify({"removed": removed, "domain": domain})

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def serve_frontend(path):
    return send_from_directory(FRONTEND_DIR, path)

@app.route("/experiment", methods=["POST"])
def experiment_route():
    """
    Runs a concurrency experiment by internally spawning N workers that call
    the same handle_fetch(cache, url) function so the inflight coalescing logic is exercised.
    Returns per-worker timings and a small summary.
    """
    data = request.get_json() or {}
    url = data.get("url")
    try:
        clients = int(data.get("clients", 5))
    except Exception:
        clients = 5

    if not url:
        return jsonify({"error": "missing url"}), 400
    if clients <= 0:
        return jsonify({"error": "invalid clients"}), 400

    results = []
    start0 = time.time()

    def worker(i):
        t0 = time.time()
        # call internal handler (this uses same cache instance)
        resp, code = handle_fetch(cache, url)
        t1 = time.time()

        # Extract headers (response may be a Flask Response)
        performed = False
        waited = False
        status = code if isinstance(code, int) else getattr(resp, "status_code", 0)
        try:
            hdrs = getattr(resp, "headers", {}) or {}
            performed = hdrs.get("X-Performed-Fetch") == "1"
            waited = hdrs.get("X-Waited") == "1"
        except Exception:
            pass

        return {
            "id": i,
            "start_ms": int((t0 - start0) * 1000),
            "end_ms": int((t1 - start0) * 1000),
            "duration_ms": int((t1 - t0) * 1000),
            "performed_fetch": bool(performed),
            "waited": bool(waited),
            "status": int(status or 0)
        }

    # Run workers concurrently (internal invocation)
    with ThreadPoolExecutor(max_workers=clients) as ex:
        futures = [ex.submit(worker, i) for i in range(1, clients + 1)]
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"id": -1, "error": str(e)})

    # compute summary
    durations = [r["duration_ms"] for r in results if "duration_ms" in r]
    network_fetches = cache.stats().get("origin_fetches") if hasattr(cache, "stats") else None
    summary = {
        "network_fetches": network_fetches,
        "avg_latency_ms": int(sum(durations) / len(durations)) if durations else 0,
        "max_latency_ms": max(durations) if durations else 0
    }

    # sort results by id for stable UI
    results_sorted = sorted([r for r in results if "id" in r and r["id"] != -1], key=lambda x: x["id"])
    return jsonify({"results": results_sorted, "summary": summary})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)