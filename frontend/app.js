// frontend/app.js
const API_BASE = "http://localhost:8000";
const urlInput = document.getElementById("urlInput");
const fetchBtn = document.getElementById("fetchBtn");
const statusMsg = document.getElementById("statusMsg");
const statsArea = document.getElementById("statsArea");
const cacheTableBody = document.querySelector("#cacheTable tbody");
const responseMeta = document.getElementById("responseMeta");
const responseBody = document.getElementById("responseBody");

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