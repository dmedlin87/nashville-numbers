"""Browser-based GUI for Nashville Numbers Converter.

Starts a local HTTP server and opens the app in the default browser.
No external dependencies required – uses only the standard library.
"""

from __future__ import annotations

import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from .converter import convert

# ---------------------------------------------------------------------------
# HTML template – embedded so the GUI is a single self-contained module.
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Nashville Numbers</title>
<style>
  /* ── Base ──────────────────────────────────────────────────────────────── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:          #0d0d1a;
    --surface:     #14142b;
    --surface2:    #1c1c38;
    --accent:      #7c5cfc;
    --accent2:     #5e3de8;
    --glow:        rgba(124, 92, 252, 0.45);
    --text:        #e8e8ff;
    --text-muted:  #8a8aaa;
    --success:     #4ade80;
    --error:       #f87171;
    --border:      rgba(124, 92, 252, 0.25);
    --radius:      14px;
    --font:        'Segoe UI', system-ui, -apple-system, sans-serif;
    --font-mono:   'Fira Code', 'Cascadia Code', 'Consolas', monospace;
    --transition:  0.22s cubic-bezier(0.4, 0, 0.2, 1);
  }

  html, body {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    overflow-x: hidden;
  }

  /* ── Starfield background ───────────────────────────────────────────────── */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
      radial-gradient(ellipse 80% 60% at 20% 10%, rgba(124,92,252,0.12) 0%, transparent 60%),
      radial-gradient(ellipse 60% 80% at 80% 90%, rgba(94,61,232,0.10) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
  }

  /* ── Layout ─────────────────────────────────────────────────────────────── */
  .page {
    position: relative;
    z-index: 1;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2rem 1rem 4rem;
    gap: 0;
  }

  /* ── Header ─────────────────────────────────────────────────────────────── */
  header {
    text-align: center;
    margin-bottom: 2.5rem;
    user-select: none;
  }

  .logo-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .logo-icon {
    font-size: 2.4rem;
    filter: drop-shadow(0 0 12px var(--glow));
  }

  h1 {
    font-size: clamp(1.8rem, 5vw, 2.8rem);
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #a78bfa 0%, #7c5cfc 40%, #c084fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-shadow: none;
  }

  .tagline {
    color: var(--text-muted);
    font-size: 0.95rem;
    letter-spacing: 0.03em;
  }

  /* ── Card ───────────────────────────────────────────────────────────────── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem;
    width: 100%;
    max-width: 720px;
    box-shadow:
      0 0 0 1px rgba(124,92,252,0.08),
      0 8px 40px rgba(0,0,0,0.55),
      0 0 80px rgba(124,92,252,0.06);
    transition: box-shadow var(--transition);
  }

  .card:hover {
    box-shadow:
      0 0 0 1px rgba(124,92,252,0.18),
      0 8px 50px rgba(0,0,0,0.65),
      0 0 100px rgba(124,92,252,0.10);
  }

  /* ── Section labels ─────────────────────────────────────────────────────── */
  .section-label {
    display: block;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.55rem;
  }

  /* ── Textarea ───────────────────────────────────────────────────────────── */
  .input-wrap {
    position: relative;
    margin-bottom: 1.25rem;
  }

  textarea {
    width: 100%;
    min-height: 110px;
    background: var(--surface2);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 1.05rem;
    line-height: 1.6;
    padding: 0.85rem 1rem;
    resize: vertical;
    outline: none;
    transition: border-color var(--transition), box-shadow var(--transition);
    caret-color: var(--accent);
  }

  textarea::placeholder { color: var(--text-muted); opacity: 0.7; }

  textarea:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--glow), 0 2px 8px rgba(0,0,0,0.3);
  }

  /* ── Controls row ───────────────────────────────────────────────────────── */
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
    margin-bottom: 1.5rem;
  }

  /* ── Convert button ─────────────────────────────────────────────────────── */
  .btn-convert {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
    color: #fff;
    font-size: 0.95rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    border: none;
    border-radius: 10px;
    padding: 0.7rem 1.6rem;
    cursor: pointer;
    transition:
      filter var(--transition),
      transform var(--transition),
      box-shadow var(--transition);
    box-shadow: 0 4px 20px rgba(124,92,252,0.4);
    white-space: nowrap;
  }

  .btn-convert:hover  { filter: brightness(1.15); transform: translateY(-1px); box-shadow: 0 6px 28px rgba(124,92,252,0.55); }
  .btn-convert:active { filter: brightness(0.95); transform: translateY(0); }
  .btn-convert.loading { opacity: 0.7; pointer-events: none; }

  .btn-convert .spinner {
    display: none;
    width: 16px; height: 16px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  .btn-convert.loading .spinner { display: block; }
  .btn-convert.loading .btn-icon { display: none; }

  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Clear button ───────────────────────────────────────────────────────── */
  .btn-clear {
    flex: 0 0 auto;
    background: transparent;
    border: 1.5px solid var(--border);
    border-radius: 10px;
    color: var(--text-muted);
    font-size: 0.88rem;
    padding: 0.65rem 1rem;
    cursor: pointer;
    transition: border-color var(--transition), color var(--transition), background var(--transition);
  }

  .btn-clear:hover {
    border-color: var(--accent);
    color: var(--text);
    background: rgba(124,92,252,0.08);
  }

  /* ── Kbd hint ───────────────────────────────────────────────────────────── */
  .kbd-hint {
    margin-left: auto;
    color: var(--text-muted);
    font-size: 0.78rem;
    white-space: nowrap;
    user-select: none;
  }

  kbd {
    display: inline-block;
    background: var(--surface2);
    border: 1px solid rgba(255,255,255,0.1);
    border-bottom-width: 2px;
    border-radius: 5px;
    padding: 0.1em 0.4em;
    font-family: var(--font-mono);
    font-size: 0.8em;
  }

  /* ── Output ─────────────────────────────────────────────────────────────── */
  .output-wrap {
    position: relative;
    min-height: 60px;
  }

  .output-box {
    background: var(--surface2);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 0.85rem 1rem;
    font-family: var(--font-mono);
    font-size: 1.05rem;
    line-height: 1.75;
    white-space: pre-wrap;
    word-break: break-word;
    min-height: 60px;
    transition: border-color var(--transition), box-shadow var(--transition), opacity var(--transition);
    position: relative;
  }

  .output-box.has-result {
    border-color: rgba(74, 222, 128, 0.35);
    box-shadow: 0 0 20px rgba(74, 222, 128, 0.08);
  }

  .output-box.has-error {
    border-color: rgba(248, 113, 113, 0.4);
    box-shadow: 0 0 20px rgba(248, 113, 113, 0.08);
  }

  .output-key {
    color: var(--text-muted);
    font-size: 0.88em;
  }

  .output-progression {
    color: var(--success);
    font-size: 1.08em;
    font-weight: 500;
  }

  .output-error {
    color: var(--error);
  }

  .output-placeholder {
    color: var(--text-muted);
    font-style: italic;
    opacity: 0.5;
    font-family: var(--font);
    font-size: 0.92rem;
  }

  /* ── Copy button ────────────────────────────────────────────────────────── */
  .btn-copy {
    position: absolute;
    top: 0.6rem;
    right: 0.6rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 7px;
    color: var(--text-muted);
    font-size: 0.78rem;
    padding: 0.3rem 0.65rem;
    cursor: pointer;
    opacity: 0;
    transition: opacity var(--transition), background var(--transition), color var(--transition);
    pointer-events: none;
  }

  .output-box.has-result:hover .btn-copy,
  .output-box.has-result .btn-copy:focus {
    opacity: 1;
    pointer-events: auto;
  }

  .btn-copy:hover { background: var(--surface2); color: var(--text); }
  .btn-copy.copied { color: var(--success); border-color: rgba(74,222,128,0.4); }

  /* ── Examples ───────────────────────────────────────────────────────────── */
  .examples-section {
    width: 100%;
    max-width: 720px;
    margin-top: 1.75rem;
  }

  .examples-header {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.75rem;
    padding-left: 0.25rem;
  }

  .examples-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.6rem;
  }

  .example-chip {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 0.65rem 0.9rem;
    cursor: pointer;
    transition: border-color var(--transition), background var(--transition), transform var(--transition), box-shadow var(--transition);
    user-select: none;
  }

  .example-chip:hover {
    border-color: var(--accent);
    background: rgba(124,92,252,0.09);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(124,92,252,0.18);
  }

  .example-chip:active { transform: translateY(0); }

  .chip-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 0.25rem;
  }

  .chip-text {
    font-family: var(--font-mono);
    font-size: 0.82rem;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* ── Footer ─────────────────────────────────────────────────────────────── */
  footer {
    margin-top: 3rem;
    color: var(--text-muted);
    font-size: 0.78rem;
    text-align: center;
    opacity: 0.5;
    user-select: none;
  }

  /* ── Animations ─────────────────────────────────────────────────────────── */
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .animate-in { animation: fadeIn 0.35s ease forwards; }

  /* ── Responsive ─────────────────────────────────────────────────────────── */
  @media (max-width: 520px) {
    .card { padding: 1.25rem; }
    .kbd-hint { display: none; }
    .examples-grid { grid-template-columns: 1fr 1fr; }
  }
</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <header class="animate-in">
    <div class="logo-row">
      <span class="logo-icon">🎸</span>
      <h1>Nashville Numbers</h1>
    </div>
    <p class="tagline">Chord progressions &harr; Nashville Number System</p>
  </header>

  <!-- Main card -->
  <div class="card animate-in" style="animation-delay:0.05s">

    <!-- Input -->
    <label for="inputArea" class="section-label">Progression Input</label>
    <div class="input-wrap">
      <textarea
        id="inputArea"
        placeholder="e.g.  C - F - G   or   1 - 4 - 5 in G   or   | C | F G | Am |"
        spellcheck="false"
        autocomplete="off"
        autocorrect="off"
      ></textarea>
    </div>

    <!-- Controls -->
    <div class="controls">
      <button class="btn-convert" id="convertBtn" onclick="doConvert()">
        <span class="btn-icon">⚡</span>
        <span class="spinner"></span>
        Convert
      </button>
      <button class="btn-clear" onclick="doClear()">Clear</button>
      <span class="kbd-hint"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> to convert</span>
    </div>

    <!-- Output -->
    <h2 class="section-label">Result</h2>
    <div class="output-wrap">
      <div class="output-box" id="outputBox" aria-live="polite">
        <span class="output-placeholder">Result will appear here&hellip;</span>
      </div>
    </div>

  </div><!-- /card -->

  <!-- Examples -->
  <div class="examples-section animate-in" style="animation-delay:0.1s">
    <div class="examples-header">Try an example</div>
    <div class="examples-grid" id="examplesGrid"></div>
  </div>

  <footer>Nashville Numbers Converter &nbsp;·&nbsp; press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to convert</footer>

</div><!-- /page -->

<script>
const EXAMPLES = [
  { label: "Chords → NNS",  text: "C - F - G" },
  { label: "Chords → NNS",  text: "| C | F G | Am |" },
  { label: "Complex chords", text: "Cmaj7#11/G, Dm7, G7" },
  { label: "NNS → Chords",  text: "1 - 4 - 5 in G" },
  { label: "NNS → Chords",  text: "Key: Eb Major; 1 6 2 5" },
  { label: "Minor key",     text: "1m - b7 - 4m - 5(7) in A minor" },
  { label: "Pop pattern",   text: "C - Am - F - G" },
  { label: "Jazz ii-V-I",   text: "Dm7 - G7 - Cmaj7" },
];

// Build example chips
const grid = document.getElementById('examplesGrid');
EXAMPLES.forEach(ex => {
  const chip = document.createElement('div');
  chip.className = 'example-chip';
  chip.innerHTML = `<div class="chip-label">${ex.label}</div><div class="chip-text">${escapeHtml(ex.text)}</div>`;
  chip.addEventListener('click', () => {
    document.getElementById('inputArea').value = ex.text;
    doConvert();
  });
  grid.appendChild(chip);
});

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function doConvert() {
  const input = document.getElementById('inputArea').value.trim();
  if (!input) return;

  const btn = document.getElementById('convertBtn');
  btn.classList.add('loading');

  fetch('/convert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input })
  })
  .then(r => r.json())
  .then(data => {
    btn.classList.remove('loading');
    renderOutput(data);
  })
  .catch(err => {
    btn.classList.remove('loading');
    renderOutput({ error: String(err) });
  });
}

function renderOutput(data) {
  const box = document.getElementById('outputBox');

  if (data.error) {
    box.className = 'output-box has-error animate-in';
    box.innerHTML = `<span class="output-error">⚠ ${escapeHtml(data.error)}</span>`;
    return;
  }

  // Parse key/progression lines for highlight
  const raw = data.result || '';
  const lines = raw.split('\n');
  let html = '';
  lines.forEach(line => {
    if (line.startsWith('Key:')) {
      html += `<span class="output-key">${escapeHtml(line)}</span>\n`;
    } else if (line === '') {
      html += '\n';
    } else {
      html += `<span class="output-progression">${escapeHtml(line)}</span>\n`;
    }
  });
  html = html.trimEnd();

  box.className = 'output-box has-result animate-in';
  box.innerHTML = html + `\n<button class="btn-copy" onclick="copyResult(this)" title="Copy to clipboard">Copy</button>`;
}

function copyResult(btn) {
  const box = document.getElementById('outputBox');
  const text = box.innerText.replace(/\nCopy$/, '').trim();
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '✓ Copied';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 1800);
  });
}

function doClear() {
  document.getElementById('inputArea').value = '';
  const box = document.getElementById('outputBox');
  box.className = 'output-box';
  box.innerHTML = '<span class="output-placeholder">Result will appear here&hellip;</span>';
  document.getElementById('inputArea').focus();
}

// Keyboard shortcut
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    doConvert();
  }
});

// Auto-focus input
window.addEventListener('load', () => document.getElementById('inputArea').focus());
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """Minimal request handler serving the single-page app and a JSON API."""

    def log_message(self, format: str, *args: object) -> None:  # silence access logs
        pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(_HTML)
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/convert":
            self._send_json({"error": "not found"}, status=404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON in request body"}, status=400)
            return
        try:
            input_text = str(payload.get("input", "")).strip()
            if not input_text:
                self._send_json({"error": "Empty input"})
                return
            result = convert(input_text)
            self._send_json({"result": result})
        except (ValueError, KeyError, TypeError) as exc:
            self._send_json({"error": str(exc)})

    def _send_html(self, html: str) -> None:
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj: dict, status: int = 200) -> None:
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def _find_free_port(start: int = 8765) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError(f"Unable to find an available port after 100 attempts (starting from {start})")


def main() -> None:
    port = _find_free_port()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Nashville Numbers GUI → {url}")
    print("Press Ctrl-C to stop.")

    # Open browser after a short delay so the server is ready
    threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
