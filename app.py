#!/usr/bin/env python3
"""
Absent Pianist — Web Interface for Kevin

Simple Flask server that lets Kevin generate hymn accompaniments
from a browser without touching the command line.

Usage: python3 app.py
Then open: http://localhost:5111
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Queue, Empty

from flask import Flask, Response, jsonify, send_from_directory

BASE_DIR = Path(__file__).parent.resolve()
HYMNS_FILE = BASE_DIR / "hymns.txt"
SOURCES_FILE = BASE_DIR / "hymn_sources.json"
OUTPUT_DIR = BASE_DIR / "output"

app = Flask(__name__)

# ── State ────────────────────────────────────────────────────────────

# One job at a time. Kevin doesn't need concurrency.
current_job = {"running": False, "hymn": None, "progress": []}
progress_queues: list[Queue] = []


def load_hymns():
    with open(HYMNS_FILE) as f:
        return [line.strip() for line in f if line.strip()]


def load_sources():
    if SOURCES_FILE.exists():
        with open(SOURCES_FILE) as f:
            return json.load(f)
    return {}


def slugify(name):
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def hymn_folder(index, name):
    return OUTPUT_DIR / f"{index:03d}_{slugify(name)}"


def get_hymn_status(hymns, sources):
    """Get status of each hymn: has source, has output files."""
    results = []
    for i, name in enumerate(hymns, 1):
        folder = hymn_folder(i, name)
        has_source = name in sources and sources[name].get("url", "MISSING") != "MISSING"

        files = {}
        if folder.exists():
            for f in folder.iterdir():
                files[f.name] = f.stat().st_size

        has_intro = "intro.wav" in files
        has_single = "single.wav" in files or "verse.wav" in files
        has_refrain = "refrain.wav" in files
        zip_name = f"{slugify(name)}.zip"
        has_zip = zip_name in files

        status = "ready" if (has_intro or has_single) else "not generated" if has_source else "no source"

        results.append({
            "index": i,
            "name": name,
            "slug": slugify(name),
            "has_source": has_source,
            "status": status,
            "has_intro": has_intro,
            "has_single": has_single,
            "has_refrain": has_refrain,
            "has_zip": has_zip,
            "folder": str(folder),
            "folder_name": folder.name if folder.exists() else f"{i:03d}_{slugify(name)}",
        })
    return results


def broadcast(message):
    """Send a progress message to all connected SSE clients."""
    current_job["progress"].append(message)
    dead = []
    for q in progress_queues:
        try:
            q.put_nowait(message)
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            progress_queues.remove(q)
        except ValueError:
            pass


def run_generate(hymn_name=None):
    """Run generate.py in a subprocess, streaming output to SSE clients."""
    current_job["running"] = True
    current_job["hymn"] = hymn_name or "ALL HYMNS"
    current_job["progress"] = []

    broadcast(f"Starting: {current_job['hymn']}")

    cmd = [sys.executable, str(BASE_DIR / "generate.py")]
    if hymn_name:
        cmd.append(hymn_name)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(BASE_DIR),
            bufsize=1,
        )

        for line in proc.stdout:
            line = line.rstrip()
            if line:
                broadcast(line)

        proc.wait()

        if proc.returncode == 0:
            broadcast("DONE: Generation complete!")
        else:
            broadcast(f"ERROR: Process exited with code {proc.returncode}")

    except Exception as e:
        broadcast(f"ERROR: {e}")
    finally:
        current_job["running"] = False
        broadcast("__FINISHED__")


# ── Routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML_PAGE


@app.route("/api/hymns")
def api_hymns():
    hymns = load_hymns()
    sources = load_sources()
    return jsonify(get_hymn_status(hymns, sources))


@app.route("/api/status")
def api_status():
    return jsonify({
        "running": current_job["running"],
        "hymn": current_job["hymn"],
        "progress_count": len(current_job["progress"]),
    })


@app.route("/api/generate/<hymn_name>", methods=["POST"])
def api_generate_one(hymn_name):
    if current_job["running"]:
        return jsonify({"ok": False, "error": "A generation is already running. Please wait."}), 409

    thread = threading.Thread(target=run_generate, args=(hymn_name,), daemon=True)
    thread.start()
    return jsonify({"ok": True, "hymn": hymn_name})


@app.route("/api/generate-all", methods=["POST"])
def api_generate_all():
    if current_job["running"]:
        return jsonify({"ok": False, "error": "A generation is already running. Please wait."}), 409

    thread = threading.Thread(target=run_generate, args=(None,), daemon=True)
    thread.start()
    return jsonify({"ok": True, "hymn": "ALL"})


@app.route("/api/progress")
def api_progress():
    """Server-Sent Events stream for generation progress."""
    q = Queue()
    progress_queues.append(q)

    def stream():
        try:
            # Send any existing progress first
            for msg in list(current_job["progress"]):
                yield f"data: {msg}\n\n"
            # Then stream new messages
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"data: {msg}\n\n"
                    if msg == "__FINISHED__":
                        break
                except Empty:
                    # Keep-alive
                    yield f"data: \n\n"
        finally:
            try:
                progress_queues.remove(q)
            except ValueError:
                pass

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/files/<path:filepath>")
def serve_file(filepath):
    """Serve generated files from the output directory."""
    return send_from_directory(str(OUTPUT_DIR), filepath)


# ── HTML ─────────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Absent Pianist</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: Georgia, 'Times New Roman', serif;
  background: #1a1a2e;
  color: #e0d8c8;
  min-height: 100vh;
}
.header {
  background: linear-gradient(135deg, #16213e 0%, #1a1a2e 50%, #0f3460 100%);
  border-bottom: 3px solid #e94560;
  padding: 28px 24px;
  text-align: center;
}
.header h1 {
  font-size: 36px;
  color: #e94560;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}
.header p {
  font-size: 18px;
  color: #a89b8c;
  font-style: italic;
}
.container {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}
.actions {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 28px;
  border: none;
  border-radius: 10px;
  font-family: inherit;
  font-size: 18px;
  cursor: pointer;
  transition: all 200ms ease;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-big {
  background: #e94560;
  color: white;
  font-weight: bold;
  font-size: 20px;
  padding: 16px 36px;
}
.btn-big:hover:not(:disabled) {
  background: #ff6b81;
  transform: translateY(-1px);
}
.btn-small {
  background: #16213e;
  color: #e0d8c8;
  border: 2px solid #533483;
  font-size: 15px;
  padding: 10px 20px;
}
.btn-small:hover:not(:disabled) {
  background: #533483;
  color: white;
}

.progress-box {
  display: none;
  background: #0f0f23;
  border: 2px solid #533483;
  border-radius: 12px;
  padding: 18px;
  margin-bottom: 24px;
  max-height: 300px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #7ec8e3;
}
.progress-box.active { display: block; }
.progress-box .line { padding: 2px 0; }
.progress-box .line.error { color: #e94560; font-weight: bold; }
.progress-box .line.done { color: #4ecdc4; font-weight: bold; font-size: 16px; }
.progress-box .line.info { color: #a89b8c; }

.hymn-list {
  display: grid;
  gap: 8px;
}
.hymn-card {
  display: grid;
  grid-template-columns: 40px 1fr auto;
  align-items: center;
  gap: 16px;
  padding: 14px 18px;
  background: #16213e;
  border: 1px solid #533483;
  border-radius: 10px;
  transition: all 200ms ease;
}
.hymn-card:hover {
  border-color: #e94560;
  background: #1a2744;
}
.hymn-num {
  font-size: 16px;
  color: #533483;
  font-weight: bold;
  text-align: center;
}
.hymn-info h3 {
  font-size: 18px;
  color: #e0d8c8;
  margin-bottom: 4px;
}
.hymn-status {
  font-size: 13px;
  color: #a89b8c;
}
.hymn-status.ready { color: #4ecdc4; }
.hymn-status.no-source { color: #e94560; }
.hymn-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.file-link {
  display: inline-block;
  padding: 6px 14px;
  background: #0f3460;
  color: #7ec8e3;
  text-decoration: none;
  border-radius: 6px;
  font-size: 13px;
  font-family: 'Courier New', monospace;
  transition: background 200ms ease;
}
.file-link:hover { background: #533483; color: white; }
.file-link.zip {
  background: #4ecdc4;
  color: #1a1a2e;
  font-weight: bold;
}

.spinner {
  display: inline-block;
  width: 18px; height: 18px;
  border: 3px solid #533483;
  border-top-color: #e94560;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.note {
  text-align: center;
  padding: 20px;
  color: #a89b8c;
  font-style: italic;
  font-size: 16px;
}

@media (max-width: 600px) {
  .hymn-card { grid-template-columns: 1fr; gap: 8px; }
  .hymn-num { text-align: left; }
  .container { padding: 14px; }
  .header h1 { font-size: 28px; }
}
</style>
</head>
<body>

<div class="header">
  <h1>Absent Pianist</h1>
  <p>Hymn accompaniment generator for small churches</p>
</div>

<div class="container">
  <div class="actions">
    <button class="btn btn-big" id="btn-all" onclick="generateAll()">
      Generate All Hymns
    </button>
    <button class="btn btn-small" id="btn-refresh" onclick="loadHymns()">
      Refresh List
    </button>
  </div>

  <div class="progress-box" id="progress"></div>

  <div id="hymn-list" class="hymn-list">
    <div class="note">Loading hymns...</div>
  </div>
</div>

<script>
let running = false;

async function loadHymns() {
  try {
    const res = await fetch('/api/hymns');
    const hymns = await res.json();
    const list = document.getElementById('hymn-list');

    if (hymns.length === 0) {
      list.innerHTML = '<div class="note">No hymns found in hymns.txt</div>';
      return;
    }

    list.innerHTML = hymns.map(h => {
      const statusCls = h.status === 'ready' ? 'ready' : h.status === 'no source' ? 'no-source' : '';
      const statusText = h.status === 'ready' ? 'Files ready' : h.status === 'no source' ? 'No MIDI source' : 'Not yet generated';

      let actions = '';

      // Generate button (only if has source)
      if (h.has_source) {
        actions += '<button class="btn btn-small gen-btn" onclick="generateOne(\\'' + esc(h.name) + '\\')" ' + (running ? 'disabled' : '') + '>Generate</button>';
      }

      // Download links for existing files
      if (h.has_intro) actions += '<a class="file-link" href="/files/' + h.folder_name + '/intro.wav" download>intro.wav</a>';
      if (h.has_single) {
        // Check both naming conventions
        actions += '<a class="file-link" href="/files/' + h.folder_name + '/single.wav" download>single.wav</a>';
      }
      if (h.has_refrain) actions += '<a class="file-link" href="/files/' + h.folder_name + '/refrain.wav" download>refrain.wav</a>';
      if (h.has_zip) actions += '<a class="file-link zip" href="/files/' + h.folder_name + '/' + h.slug + '.zip" download>ZIP</a>';

      return '<div class="hymn-card">' +
        '<div class="hymn-num">' + h.index + '</div>' +
        '<div class="hymn-info"><h3>' + esc(h.name) + '</h3><div class="hymn-status ' + statusCls + '">' + statusText + '</div></div>' +
        '<div class="hymn-actions">' + actions + '</div>' +
        '</div>';
    }).join('');
  } catch (err) {
    document.getElementById('hymn-list').innerHTML = '<div class="note">Error loading hymns: ' + err.message + '</div>';
  }
}

async function generateOne(name) {
  if (running) return alert('A generation is already running. Please wait for it to finish.');
  running = true;
  disableButtons();
  showProgress();

  try {
    const res = await fetch('/api/generate/' + encodeURIComponent(name), { method: 'POST' });
    const data = await res.json();
    if (!data.ok) {
      addProgressLine(data.error, 'error');
      running = false;
      enableButtons();
      return;
    }
    listenProgress();
  } catch (err) {
    addProgressLine('Error: ' + err.message, 'error');
    running = false;
    enableButtons();
  }
}

async function generateAll() {
  if (running) return alert('A generation is already running. Please wait for it to finish.');
  running = true;
  disableButtons();
  showProgress();

  try {
    const res = await fetch('/api/generate-all', { method: 'POST' });
    const data = await res.json();
    if (!data.ok) {
      addProgressLine(data.error, 'error');
      running = false;
      enableButtons();
      return;
    }
    listenProgress();
  } catch (err) {
    addProgressLine('Error: ' + err.message, 'error');
    running = false;
    enableButtons();
  }
}

function listenProgress() {
  const source = new EventSource('/api/progress');
  source.onmessage = function(event) {
    const msg = event.data;
    if (msg === '__FINISHED__') {
      source.close();
      running = false;
      enableButtons();
      addProgressLine('', 'done');
      loadHymns();
      return;
    }
    if (!msg) return; // keep-alive
    const cls = msg.startsWith('ERROR') ? 'error' : msg.startsWith('DONE') ? 'done' : 'info';
    addProgressLine(msg, cls);
  };
  source.onerror = function() {
    source.close();
    running = false;
    enableButtons();
  };
}

function showProgress() {
  const box = document.getElementById('progress');
  box.innerHTML = '';
  box.classList.add('active');
}

function addProgressLine(text, cls) {
  const box = document.getElementById('progress');
  const line = document.createElement('div');
  line.className = 'line ' + (cls || '');
  line.textContent = text;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function disableButtons() {
  document.querySelectorAll('.btn, .gen-btn').forEach(b => b.disabled = true);
}

function enableButtons() {
  document.querySelectorAll('.btn, .gen-btn').forEach(b => b.disabled = false);
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Load on start
loadHymns();

// Poll for status changes
setInterval(async () => {
  try {
    const res = await fetch('/api/status');
    const s = await res.json();
    if (!s.running && running) {
      running = false;
      enableButtons();
      loadHymns();
    }
  } catch {}
}, 5000);
</script>
</body>
</html>"""


# ── Boot ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("  Absent Pianist — Web Interface")
    print("  Open your browser to: http://localhost:5111")
    print("  Press Ctrl+C to stop")
    print()
    app.run(host="0.0.0.0", port=5111, debug=False, threaded=True)
