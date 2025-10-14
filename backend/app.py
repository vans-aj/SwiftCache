# backend/app.py
"""
SwiftCache: Multithreaded Proxy Server demonstrating OS concepts
- Thread pool & process management
- Scheduling algorithms (FCFS, SJF, RR)
- Synchronization & request coalescing
- LRU cache & memory management
"""

from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask_cors import CORS
import time
import threading
from queue import Queue, PriorityQueue
import logging

from cache.inflight_cache import InflightCache
from proxy.handlers import handle_fetch, handle_list_cache
from utils.validators import get_blocklist, add_blocklist, remove_blocklist

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(threadName)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ============================================================================
# THREAD POOL & MEMORY MANAGEMENT
# ============================================================================
CACHE_CAPACITY_BYTES = 5 * 1024 * 1024  # 5 MB
cache = InflightCache(capacity_bytes=CACHE_CAPACITY_BYTES)
executor = ThreadPoolExecutor(max_workers=8)

logger.info(f"Initialized cache with capacity: {CACHE_CAPACITY_BYTES / 1024 / 1024:.1f} MB")
logger.info(f"Thread pool initialized with 8 worker threads")

# ============================================================================
# SCHEDULING QUEUES & STATE
# ============================================================================
scheduler_queues = {
    "fcfs": Queue(),
    "sjf": PriorityQueue(),
    "rr": Queue()
}
active_scheduler = "fcfs"
scheduler_lock = threading.Lock()

logger.info(f"Scheduler initialized with {len(scheduler_queues)} algorithms")

# ============================================================================
# SCHEDULING DISPATCHER (Background Thread)
# ============================================================================

def get_job_priority(url: str) -> int:
    """Assign priority for SJF: lower number = higher priority (shorter)."""
    small_exts = ['.css', '.js', '.html', '.json']
    medium_exts = ['.jpg', '.png', '.gif', '.svg']
    large_exts = ['.mp4', '.zip', '.iso', '.pdf']
    
    for ext in small_exts:
        if url.endswith(ext):
            return 1
    for ext in medium_exts:
        if url.endswith(ext):
            return 2
    for ext in large_exts:
        if url.endswith(ext):
            return 3
    return 2

def scheduler_dispatcher():
    """
    Background thread that pulls requests from the active queue and dispatches
    to the thread pool. Demonstrates OS concepts:
    - Context switching between scheduler algorithms
    - Work queue pattern (producer-consumer)
    - Thread management via executor
    """
    logger.info("Scheduler dispatcher thread started")
    
    while True:
        try:
            with scheduler_lock:
                current_algo = active_scheduler
            
            request_queue = scheduler_queues[current_algo]
            
            # Blocking get from appropriate queue
            if current_algo == "sjf":
                priority, url, submission_time = request_queue.get()
                logger.info(f"[DISPATCH {current_algo.upper()}] Priority={priority} URL={url}")
            else:
                url, submission_time = request_queue.get()
                logger.info(f"[DISPATCH {current_algo.upper()}] URL={url}")
            
            # Submit work to thread pool
            executor.submit(handle_fetch, cache, url)
            
        except Exception as e:
            logger.error(f"Scheduler dispatcher error: {e}")
            time.sleep(1)

# Start dispatcher as daemon thread
dispatcher_thread = threading.Thread(target=scheduler_dispatcher, daemon=True)
dispatcher_thread.start()

# ============================================================================
# API ROUTES
# ============================================================================

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "SwiftCache",
        "version": "1.0"
    })

@app.route("/fetch", methods=["POST"])
def fetch_route():
    """
    Queue a fetch request using current scheduling policy.
    Demonstrates: queuing, scheduling, thread pool submission.
    """
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    
    if not url:
        return jsonify({"error": "missing url"}), 400
    
    with scheduler_lock:
        current_algo = active_scheduler
    
    queue_to_use = scheduler_queues[current_algo]
    submission_time = time.time()
    
    # Enqueue based on algorithm
    if current_algo == "sjf":
        priority = get_job_priority(url)
        queue_to_use.put((priority, url, submission_time))
    else:
        queue_to_use.put((url, submission_time))
    
    logger.info(f"[API] Queued {url} with {current_algo.upper()}")
    return jsonify({
        "message": f"Request queued with {current_algo.upper()} policy",
        "scheduler": current_algo,
        "queue_size": queue_to_use.qsize()
    }), 202

@app.route("/cache", methods=["GET"])
def cache_route():
    """Get cache statistics and contents."""
    return handle_list_cache(cache)

@app.route("/scheduler", methods=["GET"])
def get_scheduler():
    """Get current scheduler policy."""
    with scheduler_lock:
        algo = active_scheduler
    return jsonify({
        "current_algorithm": algo,
        "available": list(scheduler_queues.keys())
    })

@app.route("/scheduler", methods=["PUT"])
def set_scheduler():
    """Change scheduling algorithm at runtime."""
    global active_scheduler
    data = request.get_json() or {}
    algo = data.get("algorithm", "").lower()
    
    if algo not in scheduler_queues:
        return jsonify({"error": "unknown algorithm"}), 400
    
    with scheduler_lock:
        if active_scheduler != algo:
            logger.info(f"[SCHEDULER] Changed {active_scheduler.upper()} → {algo.upper()}")
            active_scheduler = algo
    
    return jsonify({
        "message": f"Scheduler changed to {algo.upper()}",
        "current_algorithm": algo
    })

@app.route("/admin/blocklist", methods=["GET"])
def admin_blocklist_get():
    """Get current blocklist."""
    return jsonify({"blocklist": get_blocklist()})

@app.route("/admin/blocklist", methods=["POST"])
def admin_blocklist_add():
    """Add domain to blocklist."""
    data = request.get_json() or {}
    domain = data.get("domain", "").strip()
    
    if not domain:
        return jsonify({"error": "missing domain"}), 400
    
    added = add_blocklist(domain)
    status = 201 if added else 409
    
    return jsonify({
        "added": added,
        "domain": domain,
        "blocklist": get_blocklist()
    }), status

@app.route("/admin/blocklist", methods=["DELETE"])
def admin_blocklist_remove():
    """Remove domain from blocklist."""
    data = request.get_json() or {}
    domain = data.get("domain", "").strip()
    
    if not domain:
        return jsonify({"error": "missing domain"}), 400
    
    removed = remove_blocklist(domain)
    status = 200 if removed else 404
    
    return jsonify({
        "removed": removed,
        "domain": domain,
        "blocklist": get_blocklist()
    }), status

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    logger.info("Starting SwiftCache server on 0.0.0.0:8000")
    app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False, threaded=True)