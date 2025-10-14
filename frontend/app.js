const API = 'http://127.0.0.1:8000';
const log = [];

function addLog(msg, type = 'info') {
    const now = new Date().toLocaleTimeString();
    const line = `[${now}] ${msg}`;
    log.push({ msg: line, type });
    if (log.length > 50) log.shift();
    
    const logArea = document.getElementById('logArea');
    logArea.innerHTML = log.map(l => 
        `<div class="log-line log-${l.type}">${l.msg}</div>`
    ).join('');
    logArea.scrollTop = logArea.scrollHeight;
}

async function fetchUrl() {
    const url = document.getElementById('urlInput').value.trim();
    if (!url) return showMsg('fetchMsg', 'error', 'Enter a URL');
    
    showMsg('fetchMsg', 'info', 'Queuing request...');
    addLog(`Queuing: ${url}`, 'info');
    
    try {
        const res = await fetch(`${API}/fetch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        
        const data = await res.json();
        if (res.ok) {
            showMsg('fetchMsg', 'success', `Request queued (${data.scheduler}) - Queue: ${data.queue_size}`);
            addLog(`✓ Queued with ${data.scheduler}`, 'info');
        } else {
            showMsg('fetchMsg', 'error', data.error);
            addLog(`✗ Error: ${data.error}`, 'error');
        }
    } catch (e) {
        showMsg('fetchMsg', 'error', 'Server connection failed');
        addLog(`✗ Connection error: ${e.message}`, 'error');
    }
}

async function changeScheduler() {
    const algo = document.querySelector('input[name="algo"]:checked').value;
    addLog(`Changing scheduler to ${algo.toUpperCase()}`, 'info');
    
    try {
        const res = await fetch(`${API}/scheduler`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ algorithm: algo })
        });
        
        const data = await res.json();
        showMsg('schedulerMsg', 'success', data.message);
        addLog(`✓ Scheduler changed to ${algo}`, 'info');
    } catch (e) {
        showMsg('schedulerMsg', 'error', 'Failed to change scheduler');
        addLog(`✗ Scheduler change failed`, 'error');
    }
}

async function updateStats() {
    try {
        const res = await fetch(`${API}/cache`);
        const data = await res.json();
        const stats = data.stats;
        
        const usageMB = (stats.current_usage_bytes / 1024 / 1024).toFixed(2);
        const capacityMB = (stats.capacity_bytes / 1024 / 1024).toFixed(2);
        document.getElementById('cacheUsage').textContent = `${usageMB} / ${capacityMB} MB`;
        
        const total = stats.hits + stats.misses;
        const ratio = total > 0 ? ((stats.hits / total) * 100).toFixed(1) : 0;
        document.getElementById('hitRatio').textContent = `${ratio}%`;
        
        document.getElementById('itemCount').textContent = stats.items;
        document.getElementById('inflightCount').textContent = stats.inflight_requests || 0;
        
        const tbody = document.getElementById('cacheTable');
        tbody.innerHTML = data.items.map(item => `
            <tr>
                <td style="max-width: 400px; word-break: break-all;">${item.url}</td>
                <td>${(item.size / 1024).toFixed(1)} KB</td>
                <td>${new Date(item.created_at * 1000).toLocaleTimeString()}</td>
            </tr>
        `).join('');
    } catch (e) {
        // Silently fail
    }
}

function showMsg(id, type, text) {
    const el = document.getElementById(id);
    el.textContent = text;
    el.className = `message show ${type}`;
}

function getSchedulerInfo() {
    fetch(`${API}/scheduler`).then(r => r.json()).then(data => {
        document.getElementById('schedulerInfo').textContent = 
            `Current: ${data.current_algorithm.toUpperCase()}`;
    }).catch(() => {});
}

document.getElementById('urlInput').addEventListener('keypress', e => {
    if (e.key === 'Enter') fetchUrl();
});

addLog('SwiftCache initialized', 'info');
getSchedulerInfo();
setInterval(updateStats, 2000);
setInterval(getSchedulerInfo, 5000);
updateStats();
