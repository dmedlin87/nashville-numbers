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
    text-align: left;
    width: 100%;
    font-family: inherit;
    color: inherit;
    display: block;
  }

  .example-chip:hover,
  .example-chip:focus-visible {
    border-color: var(--accent);
    background: rgba(124,92,252,0.09);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(124,92,252,0.18);
    outline: none;
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
  .animate-in-delay { animation: fadeIn 0.35s ease 0.05s both; }
  .animate-in-delay2 { animation: fadeIn 0.35s ease 0.1s both; }

  /* ── Fretboard ──────────────────────────────────────────────────────────── */
  .fretboard-section {
    margin-top: 2rem;
    padding-top: 1.5rem;
    border-top: 1px dashed var(--border);
    display: none;
  }

  .fretboard-section.active {
    display: block;
    animation: fadeIn 0.4s ease forwards;
  }

  .fb-controls {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: center;
    margin-bottom: 1.25rem;
  }

  .fb-group {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--surface2);
    padding: 0.35rem 0.75rem;
    border-radius: 8px;
    border: 1px solid var(--border);
  }

  .fb-group label {
    font-size: 0.65rem;
    font-weight: 800;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .fb-select {
    background: transparent;
    color: var(--text);
    border: none;
    font-size: 0.85rem;
    font-weight: 600;
    outline: none;
    cursor: pointer;
  }

  .fb-select option { background: var(--surface2); }

  .fb-filter-group {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    background: var(--surface2);
    padding: 0.35rem 0.75rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    flex-wrap: wrap;
  }

  .fb-filter-group-label {
    font-size: 0.65rem;
    font-weight: 800;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-right: 0.25rem;
    white-space: nowrap;
  }

  .fb-filter-chip {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text-muted);
    font-size: 0.75rem;
    font-weight: 700;
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all var(--transition);
  }

  .fb-filter-chip.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .fretboard-outer {
    width: 100%;
    overflow-x: auto;
    padding-bottom: 1rem;
    border-radius: 8px;
  }

  .fretboard {
    position: relative;
    background: #1e1e1e;
    border: 4px solid #3a3a3a;
    border-radius: 6px;
    height: 160px;
    min-width: 900px;
    margin: 10px 0;
    display: flex;
    flex-direction: column;
    justify-content: space-around;
  }

  .fb-string-line {
    position: absolute;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(to bottom, #eee 0%, #999 50%, #666 100%);
    z-index: 1;
    pointer-events: none;
  }

  .fb-fret-line {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 3px;
    background: linear-gradient(to right, #ccc 0%, #888 50%, #444 100%);
    z-index: 2;
  }

  .fb-fret-line.nut {
    width: 8px;
    background: #e5e5e5;
    left: 0;
  }

  .fb-marker {
    position: absolute;
    width: 14px;
    height: 14px;
    background: rgba(255,255,255,0.1);
    border-radius: 50%;
    z-index: 0;
    top: 50%;
    transform: translate(-50%, -50%);
  }

  .fb-note-dot {
    position: absolute;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    z-index: 10;
    transform: translate(-50%, -50%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7rem;
    font-weight: 800;
    color: #fff;
    box-shadow: 0 2px 5px rgba(0,0,0,0.4);
    transition: all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    cursor: default;
  }

  .fb-note-dot.tonic { background: #f59e0b; box-shadow: 0 0 10px rgba(245, 158, 11, 0.5); }
  .fb-note-dot.degree-1 { background: #ef4444; }
  .fb-note-dot.degree-2 { background: #f97316; }
  .fb-note-dot.degree-3 { background: #f59e0b; }
  .fb-note-dot.degree-4 { background: #10b981; }
  .fb-note-dot.degree-5 { background: #3b82f6; }
  .fb-note-dot.degree-6 { background: #8b5cf6; }
  .fb-note-dot.degree-7 { background: #ec4899; }

  .fb-note-dot.dimmed { opacity: 0.2; transform: translate(-50%, -50%) scale(0.8); }

  .interactive-token {
    cursor: pointer;
    border-bottom: 1px dashed transparent;
    transition: border-color 0.2s, background 0.2s;
    border-radius: 3px;
  }
  .interactive-token:hover {
    border-bottom-color: currentColor;
    background: rgba(124, 92, 252, 0.1);
  }
  .interactive-token:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
    background: rgba(124, 92, 252, 0.1);
  }
  .interactive-token.active-highlight {
    background: rgba(124, 92, 252, 0.25);
    border-bottom: 2px solid var(--accent);
  }

  /* ── Output blocks ──────────────────────────────────────────────────────── */
  .output-block {
    margin-bottom: 1rem;
  }
  .output-block:last-child {
    margin-bottom: 0;
  }

  /* ── Fretboard preset chip ──────────────────────────────────────────────── */
  .fb-filter-chip.preset {
    margin-left: 0.75rem;
    border-style: dashed;
    color: var(--accent);
  }

  .fb-filter-chip.preset:hover {
    background: rgba(124, 92, 252, 0.15);
    border-color: var(--accent);
  }

  /* ── Responsive ─────────────────────────────────────────────────────────── */
  @media (max-width: 520px) {
    .card { padding: 1.25rem; }
    .kbd-hint { display: none; }
    .examples-grid { grid-template-columns: 1fr 1fr; }
    .fb-controls { gap: 0.6rem; }
    .fb-filter-group { flex-wrap: wrap; }
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
  <div class="card animate-in-delay">

    <!-- Input -->
    <div class="section-label">Progression Input</div>
    <div class="input-wrap">
      <textarea
        aria-label="Chord progression input"
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
      <button class="btn-clear" onclick="doClear()" aria-label="Clear input and result">Clear</button>
      <span class="kbd-hint"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> to convert</span>
    </div>

    <!-- Output -->
    <div class="section-label">Result</div>
    <div class="output-wrap">
      <div class="output-box" id="outputBox" aria-live="polite">
        <span class="output-placeholder">Result will appear here&hellip;</span>
      </div>
    </div>

    <!-- Fretboard -->
    <div class="fretboard-section" id="fbSection">
      <div class="section-label">Fretboard Visualization</div>

      <div class="fb-controls">
        <div class="fb-group">
          <label for="instrumentSelect">Instrument</label>
          <select id="instrumentSelect" class="fb-select" onchange="updateFretboard()">
            <option value="guitar">Guitar (6-string)</option>
            <option value="bass">Bass (4-string)</option>
            <option value="bass5">Bass (5-string)</option>
          </select>
        </div>

        <div class="fb-group">
          <label for="viewModeSelect">Mode</label>
          <select id="viewModeSelect" class="fb-select" onchange="updateFretboard()">
            <option value="scale">Full Scale</option>
            <option value="chord">Selected Chord</option>
          </select>
        </div>

        <div class="fb-filter-group" id="fbFilters">
          <span class="fb-filter-group-label">Degrees</span>
          <button class="fb-filter-chip active" data-degree="1" aria-label="Toggle degree 1" onclick="toggleDegree(1)">1</button>
          <button class="fb-filter-chip active" data-degree="2" aria-label="Toggle degree 2" onclick="toggleDegree(2)">2</button>
          <button class="fb-filter-chip active" data-degree="3" aria-label="Toggle degree 3" onclick="toggleDegree(3)">3</button>
          <button class="fb-filter-chip active" data-degree="4" aria-label="Toggle degree 4" onclick="toggleDegree(4)">4</button>
          <button class="fb-filter-chip active" data-degree="5" aria-label="Toggle degree 5" onclick="toggleDegree(5)">5</button>
          <button class="fb-filter-chip active" data-degree="6" aria-label="Toggle degree 6" onclick="toggleDegree(6)">6</button>
          <button class="fb-filter-chip active" data-degree="7" aria-label="Toggle degree 7" onclick="toggleDegree(7)">7</button>
          <button class="fb-filter-chip preset" aria-label="Show degrees 1, 3, and 6 only" onclick="applyPreset([1,3,6])">1-3-6</button>
        </div>
      </div>

      <div class="fretboard-outer">
        <div class="fretboard" id="fretboard">
          <!-- Strings and frets generated by JS -->
        </div>
      </div>
    </div>

  </div><!-- /card -->

  <!-- Examples -->
  <div class="examples-section animate-in-delay2">
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
  const chip = document.createElement('button');
  chip.type = 'button';
  chip.className = 'example-chip';
  chip.setAttribute('aria-label', `Example: ${ex.label}, ${ex.text}`);
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
  const fbSection = document.getElementById('fbSection');

  if (data.error) {
    box.className = 'output-box has-error animate-in';
    box.innerHTML = `<span class="output-error">⚠ ${escapeHtml(data.error)}</span>`;
    fbSection.classList.remove('active');
    return;
  }

  const raw = data.result || '';
  const blocks = raw.split('\n\n');
  let html = '';

  blocks.forEach(block => {
    const lines = block.split('\n');
    if (lines.length === 0) return;

    let keyLine = lines[0];
    let progressionLines = lines.slice(1);

    const keyMatch = keyLine.match(/^Key:\s+([A-G](?:#|b)?)\s+([a-zA-Z]+)/i);
    const keyTonic = keyMatch ? keyMatch[1] : "C";
    const keyMode = (keyMatch && keyMatch[2].toLowerCase().startsWith('min')) ? "Minor" : "Major";

    html += `<div class="output-block">`;
    html += `<span class="output-key interactive-token" onclick="highlightToken(this, {type:'key', keyTonic:'${keyTonic}', keyMode:'${keyMode}'})">${escapeHtml(keyLine)}</span>\n`;

    progressionLines.forEach(line => {
      const tokens = line.split(/(\s+|[-|,|\|]|\/)/);
      tokens.forEach(token => {
        if (!token.trim() || /^[-,|\|/]$/.test(token)) {
          html += escapeHtml(token);
          return;
        }

        const isNns = /^[#b]?[1-7]/.test(token);
        const isChord = /^[A-G]/.test(token);

        if (isNns || isChord) {
          const type = isNns ? 'nns' : 'chord';
          const rootMatch = isChord ? token.match(/^[A-G](?:#|b)?/) : null;
          const root = rootMatch ? rootMatch[0] : null;
          const dataJson = JSON.stringify({
            type,
            text: token,
            root,
            keyTonic,
            keyMode
          }).replace(/"/g, '&quot;');

          html += `<span class="output-progression interactive-token" onclick="highlightToken(this, ${dataJson})">${escapeHtml(token)}</span>`;
        } else {
          html += escapeHtml(token);
        }
      });
      html += '\n';
    });
    html += `</div>`;
  });

  box.className = 'output-box has-result animate-in';
  box.innerHTML = html.trimEnd() + `\n<button class="btn-copy" onclick="copyResult(this)" title="Copy to clipboard">Copy</button>`;

  fbSection.classList.add('active');

  const firstToken = box.querySelector('.interactive-token');
  if (firstToken) firstToken.click();
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
  document.getElementById('fbSection').classList.remove('active');
  selectedChord = null;
  document.getElementById('inputArea').focus();
}

// ── Fretboard Logic ────────────────────────────────────────────────────────

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const SCALE_DEGREES = {
  "Major": [0, 2, 4, 5, 7, 9, 11],
  "Minor": [0, 2, 3, 5, 7, 8, 10]
};

const TUNINGS = {
  guitar: [4, 11, 7, 2, 9, 4], // E B G D A E
  bass: [7, 2, 9, 4],       // G D A E
  bass5: [7, 2, 9, 4, 11]    // G D A E B
};

let currentKey = { tonic: "C", mode: "Major" };
let selectedChord = null;
let visibleDegrees = new Set([1, 2, 3, 4, 5, 6, 7]);

function getNoteValue(name) {
  const map = {
    "C":0,"B#":0,"C#":1,"Db":1,"D":2,"D#":3,"Eb":3,"E":4,"Fb":4,"F":5,"E#":5,
    "F#":6,"Gb":6,"G":7,"G#":8,"Ab":8,"A":9,"A#":10,"Bb":10,"B":11,"Cb":11
  };
  return map[name.replace(/maj7|mmaj7|min|maj|dim|aug|sus2|sus4|m|7|6|9|11|13|add\d+|[#b]\d+/gi, "")] ?? 0;
}

function updateFretboard() {
  const container = document.getElementById('fretboard');
  const instrument = document.getElementById('instrumentSelect').value;
  const viewMode = document.getElementById('viewModeSelect').value;
  const tuning = TUNINGS[instrument];
  const numFrets = 15;

  container.innerHTML = '';
  container.style.height = (tuning.length * 28) + 'px';

  // Draw frets
  for (let i = 0; i <= numFrets; i++) {
    const fret = document.createElement('div');
    fret.className = i === 0 ? 'fb-fret-line nut' : 'fb-fret-line';
    fret.style.left = (i * (100 / numFrets)) + '%';
    container.appendChild(fret);

    // Marker dots
    if ([3, 5, 7, 9].includes(i)) {
      const marker = document.createElement('div');
      marker.className = 'fb-marker';
      marker.style.left = ((i - 0.5) * (100 / numFrets)) + '%';
      container.appendChild(marker);
    } else if (i === 12) {
      [0.25, 0.75].forEach(pos => {
        const marker = document.createElement('div');
        marker.className = 'fb-marker';
        marker.style.left = ((i - 0.5) * (100 / numFrets)) + '%';
        marker.style.top = (pos * 100) + '%';
        container.appendChild(marker);
      });
    }
  }

  // Draw strings and notes
  tuning.forEach((openNote, stringIdx) => {
    const stringLine = document.createElement('div');
    stringLine.className = 'fb-string-line';
    stringLine.style.top = ((stringIdx + 0.5) * (100 / tuning.length)) + '%';
    container.appendChild(stringLine);

    for (let fret = 0; fret <= numFrets; fret++) {
      const noteVal = (openNote + fret) % 12;
      const degreeInfo = getDegreeInKey(noteVal, currentKey);

      if (!degreeInfo) continue;

      let shouldShow = false;
      let label = degreeInfo.degree;
      let isTonic = degreeInfo.degree === 1;

      if (viewMode === 'scale') {
        shouldShow = visibleDegrees.has(degreeInfo.degree);
      } else if (viewMode === 'chord' && selectedChord) {
        const chordNotes = getChordNotes(selectedChord, currentKey);
        shouldShow = chordNotes.includes(noteVal);
        isTonic = noteVal === getNoteValue(selectedChord.root);
      }

      if (shouldShow) {
        const dot = document.createElement('div');
        const isSelectedTonic = isTonic || (viewMode === 'chord' && selectedChord && selectedChord.type === 'nns' && degreeInfo.degree === parseInt(selectedChord.text.match(/[1-7]/)[0]));
        dot.className = `fb-note-dot degree-${degreeInfo.degree} ${isSelectedTonic ? 'tonic' : ''}`;
        dot.style.left = ((fret === 0 ? 0.5 : fret - 0.5) * (100 / numFrets)) + '%';
        dot.style.top = ((stringIdx + 0.5) * (100 / tuning.length)) + '%';
        dot.textContent = label;
        container.appendChild(dot);
      }
    }
  });
}

function getDegreeInKey(noteVal, key) {
  const tonicVal = getNoteValue(key.tonic);
  const diff = (noteVal - tonicVal + 12) % 12;
  const scale = SCALE_DEGREES[key.mode];
  const idx = scale.indexOf(diff);
  return idx !== -1 ? { degree: idx + 1, val: noteVal } : null;
}

function getChordNotes(chord, key) {
  // Simple chord note derivation
  let rootVal;
  if (chord.type === 'nns') {
    const steps = {"1":0,"b2":1,"2":2,"b3":3,"3":4,"4":5,"#4":6,"5":7,"b6":8,"6":9,"b7":10,"7":11};
    const degMatch = chord.text.match(/^[#b]?[1-7]/);
    rootVal = (getNoteValue(key.tonic) + (steps[degMatch[0]] || 0)) % 12;
  } else {
    rootVal = getNoteValue(chord.root);
  }

  // Basic triad/7th logic
  const notes = [rootVal];
  const text = chord.text.toLowerCase();

  // Third
  if (text.includes('m') && !text.includes('maj')) notes.push((rootVal + 3) % 12);
  else if (text.includes('dim')) notes.push((rootVal + 3) % 12);
  else if (text.includes('sus4')) notes.push((rootVal + 5) % 12);
  else if (text.includes('sus2')) notes.push((rootVal + 2) % 12);
  else notes.push((rootVal + 4) % 12);

  // Fifth
  if (text.includes('dim') || text.includes('b5')) notes.push((rootVal + 6) % 12);
  else if (text.includes('aug') || text.includes('+')) notes.push((rootVal + 8) % 12);
  else notes.push((rootVal + 7) % 12);

  // Seventh
  if (text.includes('maj7')) notes.push((rootVal + 11) % 12);
  else if (text.includes('7')) notes.push((rootVal + 10) % 12);

  return notes;
}

function toggleDegree(d) {
  if (visibleDegrees.has(d)) visibleDegrees.delete(d);
  else visibleDegrees.add(d);

  _syncFilterUI();
  updateFretboard();
}

function applyPreset(degrees) {
  visibleDegrees = new Set(degrees);
  _syncFilterUI();
  updateFretboard();
}

function _syncFilterUI() {
  document.querySelectorAll('.fb-filter-chip[data-degree]').forEach(btn => {
    const d = parseInt(btn.dataset.degree);
    btn.classList.toggle('active', visibleDegrees.has(d));
  });
}

function highlightToken(tokenEl, data) {
  document.querySelectorAll('.interactive-token').forEach(el => el.classList.remove('active-highlight'));
  tokenEl.classList.add('active-highlight');

  currentKey = { tonic: data.keyTonic, mode: data.keyMode };
  if (data.type === 'chord' || data.type === 'nns') {
    selectedChord = data;
    document.getElementById('viewModeSelect').value = 'chord';
  } else {
    selectedChord = null;
    document.getElementById('viewModeSelect').value = 'scale';
  }
  updateFretboard();
}

// Keyboard shortcut
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    doConvert();
  }
});

// Auto-focus input
window.addEventListener('load', () => {
  document.getElementById('inputArea').focus();
});
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


def _start_server(server: HTTPServer) -> None:
    try:
        server.serve_forever()
    except Exception:
        pass


def main() -> None:
    port = _find_free_port()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Nashville Numbers GUI serving at {url}")

    # Run the HTTP server in a background thread
    server_thread = threading.Thread(target=_start_server, args=(server,), daemon=True)
    server_thread.start()

    try:
        import webview

        # Open as a native desktop application window
        webview.create_window(
            "Nashville Numbers",
            url,
            width=800,
            height=700,
            min_size=(400, 500)
        )
        webview.start()

    except (ImportError, Exception) as e:
        if isinstance(e, ImportError):
            print("pywebview not installed. Falling back to default browser.")
        else:
            print(f"Failed to start native window: {e}. Falling back to default browser.")
        print("Press Ctrl-C to stop.")

        # Open browser after a short delay so the server is ready
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

        try:
            # Block the main thread to keep the daemon server thread alive
            while True:
                threading.Event().wait(3600)
        except KeyboardInterrupt:
            print("\nStopped.")

    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1.0)


if __name__ == "__main__":
    main()
