# backend/scheduler/algorithms.py
from typing import List, Dict

def fcfs(processes: List[Dict]) -> List[Dict]:
    """
    First Come First Serve scheduling.
    Each process: {"id": str, "arrival": int, "burst": int}
    Returns: [{"id":..., "start":..., "end":...}, ...] for Gantt chart.
    """
    processes = sorted(processes, key=lambda p: p["arrival"])
    time = 0
    timeline = []

    for p in processes:
        if time < p["arrival"]:
            time = p["arrival"]  # idle until process arrives
        start = time
        end = time + p["burst"]
        timeline.append({"id": p["id"], "start": start, "end": end})
        time = end
    return timeline

def sjf(processes: List[Dict]) -> List[Dict]:
    """
    Non-preemptive Shortest Job First.
    """
    processes = sorted(processes, key=lambda p: (p["arrival"], p["burst"]))
    n = len(processes)
    time = 0
    finished = [False] * n
    timeline = []
    done = 0

    while done < n:
        # pick from arrived, unfinished processes
        available = [(i, p) for i, p in enumerate(processes) if not finished[i] and p["arrival"] <= time]
        if not available:
            time += 1
            continue
        idx, shortest = min(available, key=lambda x: x[1]["burst"])
        start = time
        end = time + shortest["burst"]
        timeline.append({"id": shortest["id"], "start": start, "end": end})
        time = end
        finished[idx] = True
        done += 1
    return timeline

def round_robin(processes: List[Dict], quantum: int = 2) -> List[Dict]:
    """
    Round Robin scheduling.
    """
    from collections import deque
    processes = sorted(processes, key=lambda p: p["arrival"])
    ready = deque()
    time = 0
    i = 0
    timeline = []
    remaining = {p["id"]: p["burst"] for p in processes}

    while i < len(processes) or ready:
        while i < len(processes) and processes[i]["arrival"] <= time:
            ready.append(processes[i])
            i += 1
        if not ready:
            time += 1
            continue
        p = ready.popleft()
        run = min(quantum, remaining[p["id"]])
        start = time
        end = time + run
        timeline.append({"id": p["id"], "start": start, "end": end})
        time = end
        remaining[p["id"]] -= run
        if remaining[p["id"]] > 0:
            ready.append(p)
    return timeline