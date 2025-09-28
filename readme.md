swiftcache/
├─ README.md                # overview + run instructions
├─ requirements.txt         # Flask, requests, flask-cors, etc.
│
├─ backend/                 # all server-side code
│  ├─ app.py                # Flask entrypoint (routes: /fetch, /cache, /stats)
│  │
│  ├─ cache/                # caching module
│  │  ├─ __init__.py
│  │  └─ lru_cache.py       # thread-safe LRU cache implementation
│  │
│  ├─ proxy/                # proxy-related logic
│  │  ├─ __init__.py
│  │  ├─ fetcher.py         # code to fetch URLs (requests library)
│  │  └─ handlers.py        # route handlers, integrates fetch + cache
│  │
│  ├─ utils/                # helper functions
│  │  ├─ http_utils.py      # filter headers, format responses
│  │  └─ validators.py      # validate incoming URLs (prevent SSRF etc.)
│  │
│  └─ tests/                # unit tests (later)
│     ├─ test_lru.py
│     └─ test_endpoints.py
│
├─ frontend/                # web dashboard
│  ├─ index.html            # main UI page
│  ├─ styles.css            # styling
│  └─ app.js                # JS logic (fetch URL, poll /cache & /stats)
│
└─ docs/                    # documentation (for report/presentation)
   ├─ architecture.png       # diagram
   ├─ project_approach.md
   └─ demo_script.md