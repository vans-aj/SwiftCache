// frontend/app.js
const API_BASE = "http://localhost:8000";
const urlInput = document.getElementById("urlInput");
const fetchBtn = document.getElementById("fetchBtn");
const statusMsg = document.getElementById("statusMsg");
const statsArea = document.getElementById("statsArea");
const cacheTableBody = document.querySelector("#cacheTable tbody");
const responseMeta = document.getElementById("responseMeta");
const responseBody = document.getElementById("responseBody");
const runExpBtn = document.getElementById("runExpBtn");
const expUrlInput = document.getElementById("expUrl");
const expClientsInput = document.getElementById("expClients");
const expStatus = document.getElementById("expStatus");
const expSummary = document.getElementById("expSummary");
const expTableBody = document.querySelector("#expTable tbody");

runExpBtn.onclick = runExperiment;

async function runExperiment() {
  let url = expUrlInput.value.trim();
  if (!url) return alert("Enter a URL for the experiment");
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    url = "http://" + url;
  }
  const clients = parseInt(expClientsInput.value, 10) || 5;

  // UI state
  expStatus.innerText = "Running experiment...";
  runExpBtn.disabled = true;
  expTableBody.innerHTML = "";
  expSummary.innerText = "";

  try {
    const res = await fetch(`${API_BASE}/experiment`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ url, clients })
    });

    if (!res.ok) {
      const txt = await res.text();
      let msg = txt;
      try { msg = JSON.parse(txt).detail || JSON.parse(txt).error || txt; } catch(e){ }
      expStatus.innerText = `Error: ${res.status} ${msg}`;
      return;
    }

    const j = await res.json();
    // Expected shape (see below). Render table + summary.
    renderExperimentResults(j);

  } catch (e) {
    expStatus.innerText = "Experiment failed: " + e.message;
  } finally {
    runExpBtn.disabled = false;
  }
}

function renderExperimentResults(data) {
  expStatus.innerText = "";
  if (!data || !data.results) {
    expSummary.innerText = "No results returned.";
    return;
  }

  // normalize results and compute bounds
  const results = data.results.slice().sort((a,b) => a.start_ms - b.start_ms);
  const starts = results.map(r => r.start_ms);
  const ends = results.map(r => (r.end_ms ?? (r.start_ms + (r.duration_ms||0))));
  const minStart = Math.min(...starts);
  const maxEnd = Math.max(...ends);
  const totalSpan = Math.max(1, maxEnd - minStart);

  // summary
  const s = data.summary || {};
  expSummary.innerHTML = `
    <b>Clients:</b> ${results.length} &nbsp;
    <b>Network fetches:</b> ${s.network_fetches ?? "?"} &nbsp;
    <b>Avg:</b> ${s.avg_latency_ms ?? "?"} ms &nbsp;
    <b>Max:</b> ${s.max_latency_ms ?? "?"} ms
  `;

  // timeline render
  const timeline = document.getElementById("expTimeline");
  timeline.innerHTML = ""; // clear
  results.forEach(r => {
    const row = document.createElement("div");
    row.className = "timeline-row";
    const label = document.createElement("div");
    label.className = "timeline-label";
    label.innerText = `#${r.id}`;

    const barWrap = document.createElement("div");
    barWrap.className = "timeline-bar-wrap";

    const bar = document.createElement("div");
    // compute left% and width% relative to minStart..maxEnd
    const leftPct = ((r.start_ms - minStart) / totalSpan) * 100;
    const widthPct = ((r.duration_ms) / totalSpan) * 100;
    bar.className = "timeline-bar";
    bar.style.left = `${leftPct}%`;
    bar.style.width = `${Math.max(1, widthPct)}%`; // ensure visible

    // choose style
    if (r.performed_fetch) {
      bar.classList.add("fetcher");
    } else if (r.waited) {
      bar.classList.add("waiter");
    } else {
      bar.classList.add("hit");
    }

    // tooltip text inside bar (optional)
    bar.title = `id:${r.id} start:${r.start_ms}ms dur:${r.duration_ms}ms`;

    barWrap.appendChild(bar);

    const info = document.createElement("div");
    info.className = "timeline-info";
    info.innerText = `${r.duration_ms} ms ${r.performed_fetch ? "(fetcher)" : (r.waited ? "(waited)" : "(hit)")}`;

    row.appendChild(label);
    row.appendChild(barWrap);
    row.appendChild(info);
    timeline.appendChild(row);
  });

  // table render
  const tbody = document.querySelector("#expTable tbody");
  tbody.innerHTML = "";
  results.forEach(r => {
    const tr = document.createElement("tr");
    if (r.performed_fetch) tr.classList.add("fetcher-row");
    const performed = r.performed_fetch ? "YES" : "";
    const waited = r.waited ? "YES" : "";
    tr.innerHTML = `<td>${r.id}</td><td>${r.start_ms}</td><td>${r.duration_ms}</td><td>${performed}</td><td>${waited}</td><td>${r.status || ""}</td>`;
    tbody.appendChild(tr);
  });
}

async function refreshCache() {
  try {
    const res = await fetch(API_BASE + "/cache");
    if (!res.ok) throw new Error("Failed to load cache");
    const j = await res.json();
    statsArea.innerText = JSON.stringify(j.stats, null, 2);
    cacheTableBody.innerHTML = "";
    (j.items || []).forEach(it => {
      const tr = document.createElement("tr");
      const created = new Date(it.created_at * 1000).toLocaleString();
      tr.innerHTML = `<td>${it.url}</td><td>${it.size}</td><td>${created}</td>`;
      cacheTableBody.appendChild(tr);
    });
  } catch (e) {
    statsArea.innerText = "Error: " + e.message;
  }
}

async function fetchUrl() {
  let url = urlInput.value.trim();
  if (!url) { alert("Enter a URL"); return; }

  // --- auto-prepend scheme if missing ---
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    url = "http://" + url;
  }
  // ---------------------------------------

  statusMsg.innerText = "Fetching...";
  fetchBtn.disabled = true;
  try {
    const res = await fetch(API_BASE + "/fetch", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({url})
    });
    const text = await res.text();
    const cacheHit = res.headers.get("X-Cache-Hit") || "0";
    const cached = res.headers.get("X-Cached") || "0";
    responseMeta.innerHTML = `<b>Status:</b> ${res.status} &nbsp; <b>X-Cache-Hit:</b> ${cacheHit} &nbsp; <b>X-Cached:</b> ${cached}`;
    // show first 5000 chars to avoid massive output
    responseBody.innerText = text.slice(0, 5000) + (text.length>5000 ? "\n\n...truncated..." : "");
  } catch (e) {
    responseMeta.innerText = "Error: " + e.message;
    responseBody.innerText = "";
  } finally {
    statusMsg.innerText = "";
    fetchBtn.disabled = false;
    refreshCache();
  }
}

fetchBtn.onclick = fetchUrl;
urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") fetchUrl(); });

// auto refresh the cache table periodically
setInterval(refreshCache, 2000);
refreshCache();

async function loadBlocklist() {
  const res = await fetch(`${API_BASE}/admin/blocklist`);
  const data = await res.json();
  const list = document.getElementById("blocklist");
  list.innerHTML = "";
  data.blocklist.forEach(domain => {
    const li = document.createElement("li");
    li.textContent = domain + " ";
    const btn = document.createElement("button");
    btn.textContent = "Remove";
    btn.onclick = () => removeFromBlocklist(domain);
    li.appendChild(btn);
    list.appendChild(li);
  });
}

// Add domain
async function addToBlocklist() {
  const domain = document.getElementById("blockDomain").value.trim();
  if (!domain) return alert("Please enter a domain");
  await fetch(`${API_BASE}/admin/blocklist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain })
  });
  document.getElementById("blockDomain").value = "";
  loadBlocklist();
}

// Remove domain
async function removeFromBlocklist(domain) {
  await fetch(`${API_BASE}/admin/blocklist`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain })
  });
  loadBlocklist();
}

// Call on page load
loadBlocklist();