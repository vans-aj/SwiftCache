# backend/app.py
from flask import Flask, request, jsonify, send_from_directory
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask_cors import CORS
import time
import os
import threading
from queue import Queue, PriorityQueue # Make sure Queue is imported

from cache.inflight_cache import InflightCache
from proxy.handlers import handle_fetch, handle_list_cache
from utils.validators import get_blocklist, add_blocklist, remove_blocklist

app = Flask(__name__)
CORS(app)

# --- CACHE AND SCHEDULER SETUP ---
CACHE_CAPACITY_BYTES = 5 * 1024 * 1024
cache = InflightCache(capacity_bytes=CACHE_CAPACITY_BYTES)

# Thread pool for workers
executor = ThreadPoolExecutor(max_workers=8)

# Request queues and state for the live scheduler
# We use a dictionary to hold different queue types
scheduler_queues = {
    "fcfs": Queue(),
    "sjf": PriorityQueue(),
    "rr": Queue() # RR also uses a simple FIFO queue for ready processes
}
active_scheduler = "fcfs" # Start with FCFS by default
scheduler_lock = threading.Lock()

# --- SCHEDULER DISPATCHER THREAD ---

def get_job_priority(url: str) -> int:
    """Assigns a higher priority (lower number) to smaller/faster content types for SJF."""
    if any(url.endswith(ext) for ext in ['.css', '.js', '.html', '.json']):
        return 1  # High priority (shortest job)
    if any(url.endswith(ext) for ext in ['.jpg', '.png', '.gif']):
        return 2  # Medium priority
    if any(url.endswith(ext) for ext in ['.mp4', '.zip', '.iso', '.pdf']):
        return 3  # Low priority (longest job)
    return 2 # Default to medium

def scheduler_dispatcher():
    """
    This function runs in a background thread. It pulls requests from the
    active queue based on the current scheduling policy and dispatches them
    to the worker thread pool.
    """
    while True:
        with scheduler_lock:
            current_algo = active_scheduler
        
        request_queue = scheduler_queues[current_algo]

        try:
            # .get() blocks until an item is available
            if current_algo == "sjf":
                priority, url, submission_time = request_queue.get()
                print(f"[SCHEDULER - SJF] Dispatching job with priority {priority} for URL: {url}")
            else: # FCFS and RR use a standard queue
                url, submission_time = request_queue.get()
                print(f"[SCHEDULER - {current_algo.upper()}] Dispatching job for URL: {url}")

            # Submit the actual work to the thread pool
            executor.submit(handle_fetch, cache, url)
        except Exception as e:
            print(f"[SCHEDULER] Error in dispatcher loop: {e}")
            time.sleep(1) # Prevent rapid-fire errors

# Create and start the dispatcher thread when the app starts
dispatcher_thread = threading.Thread(target=scheduler_dispatcher, daemon=True)
dispatcher_thread.start()


# --- API ROUTES ---

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "name": "SwiftCache"})

@app.route("/fetch", methods=["POST"])
def fetch_route():
    data = request.get_json() or {}
    url = data.get("url")
    if not url:
        return jsonify({"error": "missing url"}), 400

    with scheduler_lock:
        current_algo = active_scheduler
    
    queue_to_use = scheduler_queues[current_algo]
    submission_time = time.time()

    if current_algo == "sjf":
        priority = get_job_priority(url)
        # PriorityQueue expects tuples to be put on it
        queue_to_use.put((priority, url, submission_time))
    else: # FCFS and RR
        queue_to_use.put((url, submission_time))

    print(f"[API] Queued request for {url} with {current_algo.upper()} scheduler.")
    return jsonify({"message": f"Request queued for processing with {current_algo.upper()} policy."}), 202


@app.route("/cache", methods=["GET"])
def cache_route():
    return handle_list_cache(cache)

from scheduler.algorithms import fcfs, sjf, round_robin

@app.route("/schedule", methods=["POST"])
def schedule_route():
    global active_scheduler
    data = request.get_json() or {}
    algo = data.get("algorithm", "fcfs")
    processes = data.get("processes", [])

    if algo not in scheduler_queues:
        return jsonify({"error": "unknown algorithm"}), 400

    # This is the key part: change the live scheduling policy
    with scheduler_lock:
        if active_scheduler != algo:
            print(f"[SCHEDULER] Changing active algorithm from {active_scheduler.upper()} to {algo.upper()}")
            active_scheduler = algo
            # Note: In a real system, you might need to handle tasks in old queues.
            # For this project, we'll just switch, and new tasks will use the new queue.

    if not processes:
         return jsonify({"message": f"Scheduler policy changed to {algo.upper()}", "timeline": []})

    # Run the simulation for the frontend visualization
    if algo == "fcfs":
        timeline = fcfs(processes)
    elif algo == "sjf":
        timeline = sjf(processes)
    elif algo == "rr":
        quantum = data.get("quantum", 2)
        timeline = round_robin(processes, quantum)
    
    return jsonify({"timeline": timeline})


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

# --- STATIC FILE SERVING ---
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def serve_frontend(path):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    # The fix is to add use_reloader=False to prevent Flask from creating a second process.
    # This ensures that all requests interact with the SAME in-memory 'cache' object.
    app.run(host="0.0.0.0", port=8000, debug=True, use_reloader=False)

