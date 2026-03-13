"""Browser-based GUI for Nashville Numbers Converter.

Starts a local HTTP server and opens the app in the default browser.
No external dependencies required – uses only the standard library.
"""

from __future__ import annotations

import secrets
import socket
import threading
import webbrowser
from collections.abc import Callable
from http.server import HTTPServer, ThreadingHTTPServer

from .audio import get_audio_service
from .converter import convert
from .gui_http import build_handler
from .music_lab import build_progression_plan
from .tone_library import ToneLibrary

MAX_INPUT_LENGTH = 1_000_000  # 1MB
MAX_UPLOAD_LENGTH = 20 * 1024 * 1024  # 20MB
MAX_ACTIVE_CONVERSIONS = 4


def _new_install_job(kind: str) -> dict[str, object]:
    return {
        "id": "",
        "kind": kind,
        "running": False,
        "stage": "",
        "pct": 0,
        "result": None,
        "error": None,
    }


class GuiApp:
    """Stateful container for the embedded GUI runtime."""

    def __init__(
        self,
        *,
        audio_service_factory: Callable[[], object] = get_audio_service,
        tone_library_factory: Callable[[], ToneLibrary] = ToneLibrary,
    ) -> None:
        self._audio_service_factory = audio_service_factory
        self._tone_library_factory = tone_library_factory
        self._audio_service: object | None = None
        self._tone_library: ToneLibrary | None = None
        self._session_id = secrets.token_urlsafe(24)
        self._session_secret = secrets.token_urlsafe(32)
        self._session_cookie_name = "nns_session"
        self._base_url = "http://127.0.0.1"
        self.runtime_install_job = _new_install_job("runtime")
        self.default_install_job = _new_install_job("default_pack")
        self.install_job_lock = threading.Lock()
        self.conversion_semaphore = threading.BoundedSemaphore(MAX_ACTIVE_CONVERSIONS)
        self.handler_class: type | None = None

    def get_audio_service(self) -> object:
        if self._audio_service is None:
            self._audio_service = self._audio_service_factory()
        return self._audio_service

    def get_initialized_audio_service(self) -> object | None:
        return self._audio_service

    def get_tone_library(self) -> ToneLibrary:
        if self._tone_library is None:
            self._tone_library = self._tone_library_factory()
        return self._tone_library

    def get_html(self) -> str:
        return _HTML

    def convert_text(self, input_text: str) -> str:
        return convert(input_text)

    def plan_arrangement(self, input_text: str, **kwargs: object) -> dict[str, object]:
        return build_progression_plan(input_text, **kwargs)

    def get_max_input_length(self) -> int:
        return MAX_INPUT_LENGTH

    def get_max_upload_length(self) -> int:
        return MAX_UPLOAD_LENGTH

    def find_free_port(self, start: int | None = None) -> int:
        if start is None:
            return 0
        for port in range(start, start + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        raise OSError(f"Unable to find an available port after 100 attempts (starting from {start})")

    def create_http_server(self, port: int, handler_class: type) -> HTTPServer:
        return ThreadingHTTPServer(("127.0.0.1", port), handler_class)

    def create_thread(
        self, target: Callable[..., object], args: tuple[object, ...], *, daemon: bool
    ) -> threading.Thread:
        return threading.Thread(target=target, args=args, daemon=daemon)

    def create_timer(self, interval: float, callback: Callable[[], object]) -> threading.Timer:
        return threading.Timer(interval, callback)

    def create_event(self) -> threading.Event:
        return threading.Event()

    def open_browser(self, url: str) -> None:
        webbrowser.open(url)

    def import_webview(self) -> object:
        import webview

        return webview

    def get_session_cookie_name(self) -> str:
        return self._session_cookie_name

    def get_expected_session_value(self) -> str:
        return f"{self._session_id}.{self._session_secret}"

    def issue_session_cookie(self) -> str:
        return (
            f"{self._session_cookie_name}={self.get_expected_session_value()}; "
            "HttpOnly; SameSite=Strict; Path=/"
        )

    def is_allowed_origin(self, origin: str | None, referer: str | None) -> bool:
        if origin:
            return origin == self._base_url
        if referer:
            return referer.startswith(self._base_url + "/") or referer == self._base_url
        return True

    def _run_install_job(self, job: dict[str, object], action: Callable[..., dict[str, object]]) -> None:
        """Background worker that calls install actions with progress updates."""

        def on_progress(pct: int, stage: str) -> None:
            with self.install_job_lock:
                job["pct"] = pct
                job["stage"] = stage

        try:
            result = action(on_progress=on_progress)
            with self.install_job_lock:
                job.update(
                    {"running": False, "pct": 100, "stage": "Done", "result": result, "error": None}
                )
        except Exception as exc:
            with self.install_job_lock:
                job.update(
                    {"running": False, "pct": 0, "stage": "Failed", "error": str(exc), "result": None}
                )

    def run_runtime_install(self) -> None:
        self._run_install_job(self.runtime_install_job, self.get_audio_service().install_runtime)

    def run_default_pack_install(self) -> None:
        self._run_install_job(self.default_install_job, lambda **_: self.get_audio_service().install_default_pack())

    def get_install_job(self, kind: str) -> dict[str, object]:
        return self.runtime_install_job if kind == "runtime" else self.default_install_job

    def get_handler_class(self) -> type:
        if self.handler_class is not None:
            return self.handler_class
        self.handler_class = build_handler(
            get_html=self.get_html,
            get_session_cookie_name=self.get_session_cookie_name,
            get_expected_session_value=self.get_expected_session_value,
            issue_session_cookie=self.issue_session_cookie,
            is_allowed_origin=self.is_allowed_origin,
            conversion_semaphore=self.conversion_semaphore,
            get_audio_service=self.get_audio_service,
            convert_text=self.convert_text,
            plan_arrangement=self.plan_arrangement,
            get_max_input_length=self.get_max_input_length,
            get_max_upload_length=self.get_max_upload_length,
            get_tone_library=self.get_tone_library,
            default_install_job=self.default_install_job,
            runtime_install_job=self.runtime_install_job,
            install_job_lock=self.install_job_lock,
            run_default_pack_install=self.run_default_pack_install,
            run_runtime_install=self.run_runtime_install,
        )
        return self.handler_class

    def panic_audio(self) -> None:
        service = self.get_initialized_audio_service()
        if service is None:
            return
        try:
            service.panic()
        except Exception:
            pass

    def create_server(self, port: int) -> HTTPServer:
        return self.create_http_server(port, self.get_handler_class())

    def serve_server(self, server: HTTPServer) -> None:
        try:
            server.serve_forever()
        except Exception:
            pass

    def start_server(self, port: int) -> tuple[HTTPServer, str, threading.Thread]:
        server = self.create_server(port)
        _host, actual_port = getattr(server, "server_address", ("127.0.0.1", port))
        url = f"http://127.0.0.1:{actual_port or port}"
        self._base_url = url
        server_thread = self.create_thread(self.serve_server, (server,), daemon=True)
        server_thread.start()
        return server, url, server_thread

    def open_native_window(self, url: str) -> None:
        webview = self.import_webview()
        webview.create_window(
            "Nashville Numbers",
            url,
            width=1440,
            height=900,
            min_size=(680, 540),
        )
        webview.start()

    def run_browser_fallback(self, url: str) -> None:
        print("Press Ctrl-C to stop.")
        self.create_timer(0.3, lambda: self.open_browser(url)).start()

        try:
            while True:
                self.create_event().wait(3600)
        except KeyboardInterrupt:
            print("\nStopped.")

    def cleanup(self, server: HTTPServer, server_thread: threading.Thread) -> None:
        self.panic_audio()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1.0)

    def run(self) -> None:
        port = self.find_free_port()
        server, url, server_thread = self.start_server(port)
        print(f"Nashville Numbers GUI serving at {url}")

        try:
            self.open_native_window(url)
        except (ImportError, Exception) as exc:
            if isinstance(exc, ImportError):
                print("pywebview not installed. Falling back to default browser.")
            else:
                print(f"Failed to start native window: {exc}. Falling back to default browser.")
            self.run_browser_fallback(url)
        finally:
            self.cleanup(server, server_thread)


# ---------------------------------------------------------------------------
# HTML template – embedded so the GUI is a single self-contained module.
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Nashville Numbers</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Outfit:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
  /* ── Base ──────────────────────────────────────────────────────────────── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:          #1a1714;
    --surface:     #231f1b;
    --surface2:    #2c2722;
    --accent:      #d4915c;
    --accent2:     #c27a3f;
    --glow:        rgba(212, 145, 92, 0.35);
    --text:        #e8dfd4;
    --text-muted:  #9a8e80;
    --success:     #7bc67e;
    --error:       #d4645c;
    --border:      rgba(212, 145, 92, 0.22);
    --radius-sm:   4px;
    --radius-md:   8px;
    --radius-lg:   12px;
    --radius:      12px;
    --ls-tight:    0.04em;
    --ls-wide:     0.12em;
    --font:        'Outfit', system-ui, -apple-system, sans-serif;
    --font-mono:   'DM Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
    --transition:  0.2s cubic-bezier(0.4, 0, 0.2, 1);
    --content-max: 1700px;
    --page-gutter: clamp(0.85rem, 2vw, 2rem);
    --panel-gap:   clamp(1rem, 1.8vw, 1.5rem);
    --card-pad:    clamp(1.25rem, 1.75vw, 2rem);
    --fb-dot-size: clamp(18px, 1.15vw, 24px);
  }

  html, body {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    overflow-x: hidden;
  }

  /* ── Warm studio texture background ────────────────────────────────────── */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
      radial-gradient(ellipse 90% 50% at 15% 5%, rgba(212,145,92,0.07) 0%, transparent 55%),
      radial-gradient(ellipse 50% 70% at 85% 95%, rgba(194,122,63,0.05) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
  }

  body::after {
    content: '';
    position: fixed;
    inset: 0;
    background: url("data:image/svg+xml,%3Csvg width='4' height='4' xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='1' height='1' fill='%23ffffff' opacity='0.015'/%3E%3C/svg%3E") repeat;
    pointer-events: none;
    z-index: 0;
  }

  /* ── Layout ─────────────────────────────────────────────────────────────── */
  .page {
    position: relative;
    z-index: 1;
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: clamp(1rem, 2.25vh, 2rem) var(--page-gutter) clamp(1.5rem, 4vh, 3rem);
    gap: 0;
    width: 100%;
  }

  /* ── Header ─────────────────────────────────────────────────────────────── */
  header {
    text-align: center;
    margin-bottom: clamp(1.25rem, 3vh, 2.25rem);
    user-select: none;
    width: min(var(--content-max), 100%);
  }

  .workspace {
    width: min(var(--content-max), 100%);
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--panel-gap);
    align-items: start;
  }

  .logo-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .logo-icon {
    font-size: 2.2rem;
    filter: drop-shadow(0 2px 6px rgba(0,0,0,0.4));
  }

  h1 {
    font-size: clamp(1.7rem, 4.5vw, 2.5rem);
    font-weight: 900;
    letter-spacing: -0.03em;
    color: var(--text);
    text-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }

  h1 .hl {
    color: var(--accent);
  }

  .tagline {
    color: var(--text-muted);
    font-size: 0.88rem;
    letter-spacing: var(--ls-tight);
    font-weight: 500;
  }

  /* ── Card ───────────────────────────────────────────────────────────────── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: var(--card-pad);
    width: 100%;
    max-width: none;
    box-shadow:
      0 1px 0 0 rgba(255,255,255,0.03) inset,
      0 8px 32px rgba(0,0,0,0.45);
    transition: box-shadow var(--transition);
  }

  .card:hover {
    box-shadow:
      0 1px 0 0 rgba(255,255,255,0.04) inset,
      0 8px 40px rgba(0,0,0,0.55);
  }

  /* ── Section labels ─────────────────────────────────────────────────────── */
  .section-label {
    display: block;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: var(--ls-wide);
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
    border-radius: var(--radius-md);
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

  textarea::placeholder { color: var(--text-muted); }

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
    letter-spacing: var(--ls-tight);
    border: none;
    border-radius: var(--radius-md);
    padding: 0.7rem 1.6rem;
    cursor: pointer;
    transition:
      filter var(--transition),
      transform var(--transition),
      box-shadow var(--transition);
    box-shadow: 0 4px 20px rgba(212,145,92,0.4);
    white-space: nowrap;
  }

  .btn-convert:hover  { filter: brightness(1.15); transform: translateY(-1px); box-shadow: 0 6px 28px rgba(212,145,92,0.55); }
  .btn-convert:active { filter: brightness(0.95); transform: translateY(0); }
  .btn-convert:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
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
    border-radius: var(--radius-md);
    color: var(--text-muted);
    font-size: 0.88rem;
    padding: 0.65rem 1rem;
    cursor: pointer;
    transition: border-color var(--transition), color var(--transition), background var(--transition);
  }

  .btn-clear:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .btn-clear:hover {
    border-color: var(--accent);
    color: var(--text);
    background: rgba(212,145,92,0.08);
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
    border-radius: var(--radius-sm);
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
    border-radius: var(--radius-md);
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
    border-color: rgba(123, 198, 126, 0.35);
    box-shadow: 0 0 20px rgba(123, 198, 126, 0.08);
  }

  .output-box.has-error {
    border-color: rgba(212, 100, 92, 0.4);
    box-shadow: 0 0 20px rgba(212, 100, 92, 0.08);
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
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 0.78rem;
    padding: 0.3rem 0.65rem;
    cursor: pointer;
    opacity: 0;
    transition: opacity var(--transition), background var(--transition), color var(--transition);
    pointer-events: none;
  }

  .output-box.has-result .btn-copy {
    opacity: 0.45;
    pointer-events: auto;
  }

  .output-box.has-result:hover .btn-copy,
  .output-box.has-result .btn-copy:focus {
    opacity: 1;
  }

  .btn-copy:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .btn-copy:hover { background: var(--surface2); color: var(--text); }
  .btn-copy.copied { color: var(--success); border-color: rgba(74,222,128,0.4); }

  /* ── Examples ───────────────────────────────────────────────────────────── */
  .examples-section {
    width: 100%;
    margin-top: 1.75rem;
  }

  .examples-header {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.75rem;
    padding-left: 0.25rem;
  }

  .examples-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 0.6rem;
  }

  .example-chip {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
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
    background: rgba(212,145,92,0.09);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(212,145,92,0.18);
    outline: none;
  }

  .example-chip:active { transform: translateY(0); }

  .chip-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: var(--ls-wide);
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

  .audio-status {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .audio-status-pill {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: var(--ls-tight);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.24rem 0.65rem;
    background: rgba(212,145,92,0.08);
    color: var(--text-muted);
  }

  .audio-status-pill.ready {
    border-color: rgba(123, 198, 126, 0.45);
    color: #b3d9b5;
    background: rgba(123, 198, 126, 0.08);
  }

  .audio-status-pill.warn {
    border-color: rgba(212, 100, 92, 0.45);
    color: #e8b3ac;
    background: rgba(212, 100, 92, 0.08);
  }

  .audio-status-detail {
    width: 100%;
    font-size: 0.73rem;
    color: var(--text-muted);
    text-align: right;
  }

  .audio-install-btn {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 0.75rem;
    font-weight: 700;
    padding: 0.34rem 0.72rem;
    cursor: pointer;
    transition: all var(--transition);
  }

  .audio-install-btn:hover {
    color: var(--text);
    border-color: var(--accent);
    background: rgba(212, 145, 92, 0.12);
  }

  .audio-install-btn.loading {
    opacity: 0.65;
    pointer-events: none;
  }

  .audio-progress-wrap {
    display: flex;
    align-items: center;
    gap: 0.45rem;
  }

  .audio-progress-track {
    width: 110px;
    height: 4px;
    background: var(--surface2);
    border-radius: 2px;
    overflow: hidden;
    flex-shrink: 0;
  }

  .audio-progress-fill {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, var(--accent), #e6b882);
    border-radius: 2px;
    transition: width 0.4s ease;
  }

  .audio-progress-label {
    font-size: 0.7rem;
    color: var(--text-muted);
    white-space: nowrap;
    max-width: 160px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .fb-group {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--surface2);
    padding: 0.35rem 0.75rem;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
  }

  .fb-group label {
    font-size: 0.7rem;
    font-weight: 800;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: var(--ls-tight);
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
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    flex-wrap: wrap;
  }

  .fb-filter-group-label {
    font-size: 0.7rem;
    font-weight: 800;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: var(--ls-tight);
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
    border-radius: var(--radius-sm);
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
    overflow-x: hidden;
    padding: 0.35rem;
    margin-top: 0.25rem;
    background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(0,0,0,0.12));
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: var(--radius-sm);
  }

  .fretboard {
    position: relative;
    background: #1e1e1e;
    border: 4px solid #3a3a3a;
    border-radius: var(--radius-sm);
    height: 160px;
    width: 100%;
    min-width: 0;
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
    width: clamp(10px, 0.85vw, 14px);
    height: clamp(10px, 0.85vw, 14px);
    background: rgba(255,255,255,0.1);
    border-radius: 50%;
    z-index: 0;
    top: 50%;
    transform: translate(-50%, -50%);
  }

  .fb-note-dot {
    position: absolute;
    width: var(--fb-dot-size);
    height: var(--fb-dot-size);
    border-radius: 50%;
    z-index: 10;
    transform: translate(-50%, -50%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: clamp(0.58rem, 0.65vw, 0.72rem);
    font-weight: 800;
    color: #fff;
    box-shadow: 0 2px 5px rgba(0,0,0,0.4);
    transition: all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    cursor: default;
  }

  .fb-note-dot.playable {
    cursor: pointer;
  }

  .fb-note-dot.tonic { background: #d4915c; box-shadow: 0 0 10px rgba(212, 145, 92, 0.5); }
  .fb-note-dot.degree-1 { background: #c2553a; }
  .fb-note-dot.degree-2 { background: #d4915c; }
  .fb-note-dot.degree-3 { background: #c9a84c; }
  .fb-note-dot.degree-4 { background: #5a9e6f; }
  .fb-note-dot.degree-5 { background: #4a82a6; }
  .fb-note-dot.degree-6 { background: #8a6eb0; }
  .fb-note-dot.degree-7 { background: #b8607a; }

  .fb-note-dot.dimmed { opacity: 0.2; transform: translate(-50%, -50%) scale(0.8); }

  .interactive-token {
    cursor: pointer;
    border-bottom: 1px dashed rgba(212, 145, 92, 0.3);
    transition: border-color 0.2s, background 0.2s;
    border-radius: var(--radius-sm);
    padding: 0.05em 0.15em;
  }
  .interactive-token:hover {
    border-bottom-color: currentColor;
    background: rgba(212, 145, 92, 0.1);
  }
  .interactive-token:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
    background: rgba(212, 145, 92, 0.1);
  }
  .interactive-token.active-highlight {
    background: rgba(212, 145, 92, 0.25);
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
    background: rgba(212, 145, 92, 0.15);
    border-color: var(--accent);
  }

  /* ── Responsive ─────────────────────────────────────────────────────────── */
  @media (min-width: 1200px) {
    .workspace {
      grid-template-columns: minmax(0, 1.35fr) minmax(300px, 0.65fr);
    }

    .examples-section {
      margin-top: 0;
      position: sticky;
      top: 0.9rem;
      max-height: calc(100dvh - 2.4rem);
      overflow-y: auto;
      padding-right: 0.25rem;
    }
  }

  @media (max-width: 900px) {
    .page {
      padding-top: 0.9rem;
    }

    .examples-section {
      margin-top: 1.15rem;
    }
  }

  @media (max-width: 520px) {
    .kbd-hint { display: none; }
    .examples-grid { grid-template-columns: 1fr 1fr; }
    .fb-controls { gap: 0.6rem; }
    .fb-filter-group { flex-wrap: wrap; }
  }

  /* ── Input Tabs ──────────────────────────────────────────────────────────── */
  .input-tabs {
    display: flex;
    gap: 0.2rem;
    margin-bottom: 1rem;
    background: var(--surface2);
    border-radius: var(--radius-md);
    padding: 0.2rem;
    border: 1px solid var(--border);
  }

  .tab-btn {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    padding: 0.45rem 1rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: all var(--transition);
    font-family: inherit;
  }

  .tab-btn.active {
    background: var(--accent);
    color: #fff;
    box-shadow: 0 2px 8px rgba(212,145,92,0.35);
  }

  /* ── Builder mode toggle ─────────────────────────────────────────────────── */
  .mode-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
  }

  .mode-toggle {
    display: flex;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    overflow: hidden;
  }

  .mode-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: var(--ls-tight);
    padding: 0.45rem 0.9rem;
    cursor: pointer;
    transition: all var(--transition);
    white-space: nowrap;
    font-family: inherit;
  }

  .mode-btn.active { background: rgba(212,145,92,0.3); color: var(--text); }

  .key-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .key-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
  }

  .key-select {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-size: 0.85rem;
    font-weight: 600;
    padding: 0.3rem 0.45rem;
    outline: none;
    cursor: pointer;
  }

  /* ── Progression track ───────────────────────────────────────────────────── */
  .progression-track {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    flex-wrap: wrap;
    min-height: 46px;
    background: var(--surface2);
    border: 1.5px dashed var(--border);
    border-radius: var(--radius-md);
    padding: 0.5rem 0.7rem;
    margin-bottom: 0.6rem;
    transition: border-color var(--transition);
  }

  .progression-track.has-items {
    border-style: solid;
    border-color: rgba(212,145,92,0.5);
  }

  .progression-empty {
    color: var(--text-muted);
    font-size: 0.82rem;
    font-style: italic;
    user-select: none;
  }

  .prog-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    background: var(--accent2);
    color: #fff;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.9rem;
    font-weight: 700;
    padding: 0.22rem 0.4rem 0.22rem 0.55rem;
    animation: popIn 0.18s cubic-bezier(0.175,0.885,0.32,1.275) forwards;
  }

  .prog-chip.separator {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-muted);
    font-weight: 400;
    font-size: 0.8rem;
    padding: 0.15rem 0.3rem 0.15rem 0.4rem;
  }

  .prog-chip-del {
    background: none;
    border: none;
    color: rgba(255,255,255,0.5);
    cursor: pointer;
    font-size: 0.78rem;
    line-height: 1;
    padding: 0.35rem 0.3rem;
    margin: -0.25rem -0.2rem -0.25rem 0;
    transition: color var(--transition);
    font-family: inherit;
  }

  .prog-chip-del:hover { color: #fff; }
  .prog-chip.separator .prog-chip-del { color: rgba(200,200,200,0.35); }
  .prog-chip.separator .prog-chip-del:hover { color: var(--text-muted); }

  @keyframes popIn {
    from { transform: scale(0.7); opacity: 0; }
    to   { transform: scale(1);   opacity: 1; }
  }

  /* ── Track actions ───────────────────────────────────────────────────────── */
  .track-actions {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 0.85rem;
    flex-wrap: wrap;
    align-items: center;
  }

  .track-spacer { flex: 1; }

  .btn-undo {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 0.78rem;
    padding: 0.35rem 0.7rem;
    cursor: pointer;
    transition: all var(--transition);
    font-family: inherit;
  }

  .btn-undo:hover { border-color: rgba(212,100,92,0.5); color: var(--error); }

  /* ── Palette labels ──────────────────────────────────────────────────────── */
  .palette-label {
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.4rem;
  }

  /* ── Note palette ────────────────────────────────────────────────────────── */
  .note-palette {
    display: flex;
    gap: 0.25rem;
    flex-wrap: wrap;
    margin-bottom: 0.85rem;
  }

  .note-btn {
    background: var(--surface2);
    border: 1.5px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 0.9rem;
    font-weight: 700;
    padding: 0.5rem 0.6rem;
    cursor: pointer;
    min-width: 44px;
    min-height: 44px;
    text-align: center;
    transition: all var(--transition);
  }

  .note-btn:hover {
    border-color: var(--accent);
    background: rgba(212,145,92,0.15);
    transform: translateY(-1px);
  }

  .note-btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
    box-shadow: 0 3px 10px rgba(212,145,92,0.45);
    transform: translateY(-1px);
  }

  .note-btn.accidental { color: var(--text-muted); font-size: 0.8rem; min-width: 36px; }
  .note-btn.accidental.active { color: #fff; }

  /* ── Number palette (NNS mode) ───────────────────────────────────────────── */
  .number-palette {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
    margin-bottom: 0.85rem;
    align-items: flex-end;
  }

  .acc-col {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    align-items: center;
    margin-right: 0.15rem;
  }

  .acc-col-label {
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.1rem;
  }

  .num-btn {
    background: var(--surface2);
    border: 1.5px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-family: var(--font-mono);
    cursor: pointer;
    transition: all var(--transition);
    text-align: center;
    min-width: 46px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.05rem;
    padding: 0.4rem 0.75rem 0.35rem;
  }

  .num-btn-digit {
    font-size: 1.15rem;
    font-weight: 800;
    line-height: 1;
  }

  .num-btn-hint {
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text-muted);
    line-height: 1;
    min-height: 0.75em;
  }

  .num-btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
    box-shadow: 0 3px 10px rgba(212,145,92,0.45);
  }

  .num-btn.active .num-btn-hint { color: rgba(255,255,255,0.75); }

  .num-btn:hover:not(.active) {
    border-color: var(--accent);
    background: rgba(212,145,92,0.15);
  }

  .scale-lock-btn {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--text-muted);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 0.22rem 0.6rem;
    cursor: pointer;
    transition: all var(--transition);
    white-space: nowrap;
    font-family: inherit;
    margin-left: 0.1rem;
  }

  .scale-lock-btn.active {
    background: rgba(212,145,92,0.18);
    border-color: var(--accent);
    color: var(--text);
  }

  /* ── Scale info tooltip ──────────────────────────────────────────────────── */
  .scale-tip-wrap {
    position: relative;
    display: inline-flex;
    align-items: center;
  }

  .scale-tip-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 0.82rem;
    cursor: pointer;
    padding: 0 0.15rem;
    line-height: 1;
    font-family: inherit;
    opacity: 0.7;
    transition: opacity var(--transition);
  }

  .scale-tip-btn:hover, .scale-tip-btn:focus { opacity: 1; outline: none; }

  .scale-tip-popup {
    display: none;
    position: absolute;
    bottom: calc(100% + 7px);
    left: 50%;
    transform: translateX(-50%);
    background: var(--surface2);
    border: 1px solid rgba(212,145,92,0.35);
    border-radius: var(--radius-sm);
    padding: 0.5rem 0.7rem;
    z-index: 200;
    min-width: 230px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.35);
    pointer-events: none;
    font-family: var(--font-mono);
    font-size: 0.74rem;
    line-height: 1.7;
    white-space: pre;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .scale-tip-wrap:hover .scale-tip-popup,
  .scale-tip-wrap:focus-within .scale-tip-popup { display: flex; }

  .stt-name {
    font-family: inherit;
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 0.15rem;
    white-space: normal;
  }

  .stt-name em { color: var(--text-muted); font-style: normal; font-weight: 400; }

  .stt-row {
    color: var(--text-muted);
    display: flex;
    gap: 0.5rem;
  }

  .stt-row b { color: var(--text); font-weight: 600; flex-shrink: 0; }

  .acc-btn {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 0.8rem;
    font-weight: 700;
    padding: 0.22rem 0.4rem;
    cursor: pointer;
    transition: all var(--transition);
    white-space: nowrap;
    font-family: inherit;
  }

  .acc-btn.selected {
    background: rgba(212,145,92,0.25);
    border-color: var(--accent);
    color: var(--text);
  }

  /* ── Quality palette ─────────────────────────────────────────────────────── */
  .quality-palette {
    display: flex;
    gap: 0.25rem;
    flex-wrap: wrap;
    margin-bottom: 0.5rem;
  }

  .quality-btn {
    background: var(--surface2);
    border: 1.5px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 0.78rem;
    font-weight: 700;
    padding: 0.38rem 0.6rem;
    cursor: pointer;
    transition: all var(--transition);
  }

  .quality-btn:hover {
    border-color: var(--accent);
    color: var(--text);
    background: rgba(212,145,92,0.1);
  }

  .quality-btn.active {
    background: rgba(212,145,92,0.3);
    border-color: var(--accent);
    color: var(--text);
  }

  /* ── Music Lab ──────────────────────────────────────────────────────────── */
  .music-lab-section {
    margin-top: clamp(2.5rem, 5vh, 4rem);
    padding-top: 2rem;
    border-top: 1px solid var(--border);
  }

  .music-lab-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-start;
    margin-bottom: 1rem;
    flex-wrap: wrap;
  }

  .music-lab-title {
    font-size: clamp(1.15rem, 1.4vw, 1.45rem);
    font-weight: 800;
    letter-spacing: -0.02em;
    margin-bottom: 0.3rem;
  }

  .music-lab-copy {
    color: var(--text-muted);
    font-size: 0.9rem;
    max-width: 62ch;
    line-height: 1.55;
  }

  .lab-pill-row {
    display: flex;
    gap: 0.45rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .lab-pill {
    border-radius: 999px;
    border: 1px solid rgba(212, 145, 92, 0.22);
    background: rgba(212, 145, 92, 0.06);
    color: var(--text-muted);
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    padding: 0.35rem 0.72rem;
  }

  .music-lab-grid {
    display: grid;
    grid-template-columns: minmax(280px, 0.82fr) minmax(0, 1.18fr);
    gap: 1rem;
    align-items: start;
  }

  .lab-panel {
    background:
      linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0)),
      var(--surface2);
    border: 1px solid rgba(212, 145, 92, 0.2);
    border-radius: var(--radius-lg);
    padding: 1rem;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
  }

  .lab-summary-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.7rem;
    margin-bottom: 0.9rem;
  }

  .lab-stat {
    border: 1px solid rgba(212, 145, 92, 0.16);
    border-radius: var(--radius-lg);
    background: rgba(18, 16, 14, 0.36);
    padding: 0.75rem 0.8rem;
    min-height: 94px;
  }

  .lab-stat-label {
    display: block;
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.45rem;
  }

  .lab-stat-value {
    display: block;
    font-size: 1rem;
    font-weight: 800;
    line-height: 1.2;
    margin-bottom: 0.25rem;
  }

  .lab-stat-copy {
    display: block;
    font-size: 0.76rem;
    color: var(--text-muted);
    line-height: 1.45;
  }

  .lab-analysis {
    margin-bottom: 1rem;
    color: var(--text-muted);
    font-size: 0.82rem;
    line-height: 1.55;
  }

  .lab-controls-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.7rem;
    margin-bottom: 1rem;
  }

  .lab-field {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .lab-field-label {
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
  }

  .lab-input,
  .lab-select {
    width: 100%;
    background: rgba(18, 16, 14, 0.5);
    border: 1px solid rgba(212, 145, 92, 0.25);
    border-radius: var(--radius-md);
    color: var(--text);
    font-family: var(--font);
    font-size: 0.95rem;
    font-weight: 600;
    padding: 0.58rem 0.75rem;
    outline: none;
    transition: border-color var(--transition), box-shadow var(--transition);
  }

  .lab-input:focus,
  .lab-select:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(212, 145, 92, 0.12);
  }

  .lab-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.8rem;
    border: 1px solid rgba(212, 145, 92, 0.22);
    border-radius: var(--radius-md);
    background: rgba(18, 16, 14, 0.46);
    padding: 0.7rem 0.8rem;
    margin-bottom: 1rem;
  }

  .lab-toggle-main {
    font-size: 0.85rem;
    font-weight: 700;
  }

  .lab-toggle-sub {
    display: block;
    color: var(--text-muted);
    font-size: 0.74rem;
    font-weight: 500;
    margin-top: 0.16rem;
  }

  .lab-toggle input {
    width: 18px;
    height: 18px;
    accent-color: var(--accent);
    cursor: pointer;
    flex-shrink: 0;
  }

  .groove-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.55rem;
    margin-bottom: 1rem;
  }

  .groove-card {
    border: 1px solid rgba(212, 145, 92, 0.18);
    border-radius: var(--radius-lg);
    background: rgba(18, 16, 14, 0.36);
    color: var(--text);
    padding: 0.75rem;
    text-align: left;
    cursor: pointer;
    transition: border-color var(--transition), transform var(--transition), box-shadow var(--transition), background var(--transition);
    font-family: inherit;
  }

  .groove-card:hover,
  .groove-card:focus-visible {
    border-color: rgba(212, 145, 92, 0.5);
    background: rgba(212, 145, 92, 0.12);
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(0,0,0,0.18);
    outline: none;
  }

  .groove-card.active {
    border-color: rgba(212, 145, 92, 0.72);
    background: linear-gradient(135deg, rgba(212, 145, 92, 0.28), rgba(194, 122, 63, 0.16));
    box-shadow: 0 12px 30px rgba(194, 122, 63, 0.18);
  }

  .groove-name {
    display: block;
    font-size: 0.9rem;
    font-weight: 800;
    margin-bottom: 0.22rem;
  }

  .groove-copy {
    display: block;
    color: var(--text-muted);
    font-size: 0.73rem;
    line-height: 1.45;
  }

  .transport-row {
    display: flex;
    gap: 0.55rem;
    flex-wrap: wrap;
    align-items: center;
  }

  .btn-transport {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    border-radius: var(--radius-md);
    border: 1px solid rgba(212, 145, 92, 0.28);
    padding: 0.65rem 0.95rem;
    font-size: 0.84rem;
    font-weight: 800;
    letter-spacing: var(--ls-tight);
    cursor: pointer;
    transition: all var(--transition);
    font-family: inherit;
  }

  .btn-transport.primary {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
    color: #fff;
    border-color: transparent;
    box-shadow: 0 6px 22px rgba(212, 145, 92, 0.3);
  }

  .btn-transport.secondary {
    background: rgba(18, 16, 14, 0.45);
    color: var(--text);
  }

  .btn-transport.ghost {
    background: transparent;
    color: var(--text-muted);
  }

  .btn-transport:hover:not(:disabled) {
    transform: translateY(-1px);
    border-color: rgba(212, 145, 92, 0.55);
  }

  .btn-transport:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .btn-transport:disabled {
    opacity: 0.42;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  .btn-transport.loop-toggle {
    background: transparent;
    color: var(--text-muted);
    border: 1px solid var(--border);
    font-size: 0.8rem;
    padding: 0.55rem 0.75rem;
  }

  .btn-transport.loop-toggle.active {
    background: rgba(212, 145, 92, 0.15);
    border-color: var(--accent);
    color: var(--accent);
  }

  .lab-transport-status {
    margin-top: 0.85rem;
    border-radius: var(--radius-md);
    border: 1px solid rgba(212, 145, 92, 0.16);
    background: rgba(18, 16, 14, 0.46);
    padding: 0.7rem 0.8rem;
    font-size: 0.8rem;
    line-height: 1.45;
    color: var(--text-muted);
  }

  .lab-transport-status.ready {
    border-color: rgba(123, 198, 126, 0.35);
    color: #b3d9b5;
  }

  .lab-transport-status.warn {
    border-color: rgba(212, 100, 92, 0.4);
    color: #e8b3ac;
  }

  .lab-transport-status.busy {
    border-color: rgba(212, 145, 92, 0.4);
    color: #e8dfd4;
  }

  .timeline-shell {
    min-height: 260px;
  }

  .arrangement-placeholder {
    min-height: 240px;
    border: 1px dashed rgba(212, 145, 92, 0.25);
    border-radius: var(--radius-lg);
    background:
      radial-gradient(circle at top right, rgba(212, 145, 92, 0.13), transparent 42%),
      rgba(18, 16, 14, 0.4);
    padding: 1rem;
    color: var(--text-muted);
    display: grid;
    align-content: center;
    gap: 0.55rem;
  }

    .arrangement-placeholder strong {
      color: var(--text);
      font-size: 0.98rem;
    }

    .tone-library-panel {
      margin-top: 0.9rem;
      padding-top: 0.75rem;
      border-top: 1px solid var(--border);
    }

    .tone-library-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
    }

    .tone-library-status {
      font-size: 0.72rem;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }

    .tone-library-list {
      margin-top: 0.7rem;
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
    }

    .tone-row {
      border: 1px solid var(--border);
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.025);
      padding: 0.55rem 0.65rem;
      display: grid;
      gap: 0.45rem;
    }

    .tone-row-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
    }

    .tone-name {
      font-weight: 700;
      font-size: 0.88rem;
    }

    .tone-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem;
    }

    .tone-pill {
      border: 1px solid var(--border-strong);
      border-radius: 999px;
      padding: 0.14rem 0.42rem;
      font-size: 0.64rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-muted);
    }

    .tone-pill.compat-compatible {
      color: #7bffc9;
      border-color: rgba(123, 255, 201, 0.34);
    }

    .tone-pill.compat-warning {
      color: #ffd38e;
      border-color: rgba(255, 211, 142, 0.34);
    }

    .tone-pill.compat-unknown {
      color: #b7bbd8;
      border-color: rgba(183, 187, 216, 0.34);
    }

    .tone-pill.compat-incompatible {
      color: #ff8e98;
      border-color: rgba(255, 142, 152, 0.34);
    }

    .tone-sub {
      color: var(--text-muted);
      font-size: 0.7rem;
      letter-spacing: 0.04em;
    }

    .tone-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
    }

    .tone-select {
      background: #121229;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      padding: 0.3rem 0.45rem;
      font-size: 0.72rem;
    }

    .arrangement-sections {
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
  }

  .timeline-section {
    border: 1px solid rgba(212, 145, 92, 0.18);
    border-radius: var(--radius-lg);
    background: rgba(18, 16, 14, 0.34);
    padding: 0.85rem;
  }

  .timeline-section-head {
    display: flex;
    justify-content: space-between;
    gap: 0.65rem;
    align-items: baseline;
    margin-bottom: 0.7rem;
    flex-wrap: wrap;
  }

  .timeline-section-title {
    font-size: 0.95rem;
    font-weight: 800;
  }

  .timeline-section-copy {
    color: var(--text-muted);
    font-size: 0.76rem;
    font-weight: 600;
  }

  .timeline-bars {
    display: grid;
    gap: 0.65rem;
  }

  .timeline-bar {
    border-radius: var(--radius-lg);
    border: 1px solid rgba(212, 145, 92, 0.12);
    background: rgba(38, 34, 30, 0.72);
    padding: 0.72rem;
  }

  .timeline-bar-top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.6rem;
    margin-bottom: 0.55rem;
  }

  .timeline-bar-label {
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
  }

  .timeline-bar-preview {
    font-family: var(--font-mono);
    font-size: 0.78rem;
    color: #d4c9b8;
  }

  .timeline-slot-row {
    display: grid;
    gap: 0.5rem;
  }

  .timeline-slot {
    width: 100%;
    border-radius: var(--radius-lg);
    border: 1px solid rgba(212, 145, 92, 0.14);
    background: rgba(18, 16, 14, 0.45);
    color: var(--text);
    padding: 0.72rem 0.78rem;
    text-align: left;
    cursor: pointer;
    transition: all var(--transition);
    font-family: inherit;
  }

  .timeline-slot:hover,
  .timeline-slot:focus-visible {
    border-color: rgba(212, 145, 92, 0.55);
    transform: translateY(-1px);
    outline: none;
  }

  .timeline-slot.active {
    border-color: rgba(212, 145, 92, 0.75);
    background: rgba(212, 145, 92, 0.2);
  }

  .timeline-slot.is-playing {
    border-color: rgba(123, 198, 126, 0.7);
    background: rgba(123, 198, 126, 0.14);
    box-shadow: 0 0 0 1px rgba(123, 198, 126, 0.2);
  }

  .timeline-slot-top {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    align-items: baseline;
    margin-bottom: 0.28rem;
  }

  .timeline-slot-chord {
    font-family: var(--font-mono);
    font-size: 0.95rem;
    font-weight: 800;
  }

  .timeline-slot-timing {
    color: var(--text-muted);
    font-size: 0.7rem;
    font-weight: 700;
  }

  .timeline-slot-sub {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    flex-wrap: wrap;
    color: var(--text-muted);
    font-size: 0.7rem;
  }

  .runway-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.65rem;
    margin-top: 0.95rem;
  }

  .runway-card {
    border-radius: var(--radius-lg);
    border: 1px solid rgba(212, 145, 92, 0.16);
    background: rgba(18, 16, 14, 0.36);
    padding: 0.82rem;
  }

  .runway-label {
    display: block;
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
  }

  .runway-title {
    display: block;
    font-size: 0.88rem;
    font-weight: 800;
    margin-bottom: 0.22rem;
  }

  .runway-copy {
    display: block;
    color: var(--text-muted);
    font-size: 0.74rem;
    line-height: 1.45;
  }

  .runway-card {
    opacity: 0.55;
    position: relative;
  }

  .runway-badge {
    display: inline-block;
    font-size: 0.6rem;
    font-weight: 800;
    letter-spacing: var(--ls-wide);
    text-transform: uppercase;
    color: var(--text-muted);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.15rem 0.45rem;
    margin-left: 0.5rem;
    vertical-align: middle;
  }

  /* ── Music Lab muted hierarchy ─────────────────────────────────────────── */
  .music-lab-section .lab-panel {
    border-color: rgba(212, 145, 92, 0.12);
  }

  .music-lab-section .btn-transport.primary {
    box-shadow: 0 4px 16px rgba(212, 145, 92, 0.2);
  }

  /* ── Tab subtitles ─────────────────────────────────────────────────────── */
  .tab-subtitle {
    display: block;
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: normal;
    text-transform: none;
    color: var(--text-muted);
    margin-top: 0.15rem;
  }

  .tab-btn.active .tab-subtitle {
    color: rgba(255,255,255,0.7);
  }

  /* ── Key row disabled state ────────────────────────────────────────────── */
  .key-row.disabled {
    opacity: 0.35;
    pointer-events: none;
  }

  .key-row.disabled .key-label::after {
    content: ' (auto)';
    font-weight: 400;
    text-transform: none;
  }

  /* ── Staged chord preview ──────────────────────────────────────────────── */
  .prog-chip.staged {
    background: rgba(212, 145, 92, 0.15);
    border: 1.5px dashed var(--accent);
    color: var(--text-muted);
    animation: none;
  }

  @media (max-width: 1180px) {
    .music-lab-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  @media (max-width: 640px) {
    .lab-summary-grid,
    .lab-controls-grid,
    .groove-grid,
    .runway-grid {
      grid-template-columns: 1fr;
    }

    .timeline-bar-top,
    .timeline-section-head,
    .timeline-slot-top,
    .timeline-slot-sub {
      flex-direction: column;
      align-items: flex-start;
    }
  }
</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <header class="animate-in">
    <div class="logo-row">
      <span class="logo-icon">🎸</span>
      <h1><span class="hl">Nashville</span> Numbers</h1>
    </div>
    <p class="tagline">Chord progressions &harr; Nashville Number System</p>
  </header>

  <div class="workspace">

  <!-- Main card -->
  <div class="card animate-in-delay">

    <!-- Input tabs -->
    <div class="input-tabs" role="tablist" aria-label="Input method">
      <button class="tab-btn active" id="tabBuilder" role="tab" aria-selected="true" aria-controls="panelBuilder" onclick="switchInputTab('builder')">Builder<span class="tab-subtitle">Build chords by clicking</span></button>
      <button class="tab-btn" id="tabText" role="tab" aria-selected="false" aria-controls="panelText" onclick="switchInputTab('text')">Text<span class="tab-subtitle">Type chords directly</span></button>
    </div>

    <!-- Builder panel -->
    <div id="panelBuilder" role="tabpanel" aria-labelledby="tabBuilder">

      <!-- Mode row -->
      <div class="mode-row">
        <div class="mode-toggle" role="group" aria-label="Conversion direction">
          <button class="mode-btn active" id="modeNnsBtn" onclick="setBuilderMode('nns')" aria-pressed="true">NNS &rarr; Chords</button>
          <button class="mode-btn" id="modeChordsBtn" onclick="setBuilderMode('chords')" aria-pressed="false">Chords &rarr; NNS</button>
        </div>
        <div class="key-row" id="keyRow" aria-label="Key selection">
          <span class="key-label">Key</span>
          <select id="keyNote" class="key-select" aria-label="Key note">
            <option>C</option><option>C#</option><option>Db</option><option>D</option>
            <option>Eb</option><option>E</option><option>F</option><option>F#</option>
            <option>Gb</option><option>G</option><option>Ab</option><option>A</option>
            <option>Bb</option><option>B</option>
          </select>
          <select id="keyQuality" class="key-select" aria-label="Key scale type" onchange="onKeyQualityChange()">
            <option title="Degrees: 1 2 3 4 5 6 7 | W W H W W W H">Major</option>
            <option title="Degrees: 1 2 ♭3 4 5 ♭6 ♭7 | W H W W H W W">Minor</option>
            <option title="Degrees: 1 2 ♭3 4 5 6 ♭7 | W H W W W H W">Dorian</option>
            <option title="Degrees: 1 2 3 4 5 6 ♭7 | W W H W W H W">Mixolydian</option>
            <option title="Degrees: 1 ♭2 ♭3 4 5 ♭6 ♭7 | H W W W H W W">Phrygian</option>
            <option title="Degrees: 1 2 3 ♯4 5 6 7 | W W W H W W H">Lydian</option>
            <option title="Degrees: 1 2 ♭3 4 5 ♭6 7 | W H W W H A H">Harmonic Minor</option>
          </select>
          <span class="scale-tip-wrap">
            <button type="button" class="scale-tip-btn" tabindex="0"
              aria-label="Scale interval information">&#x24D8;</button>
            <span class="scale-tip-popup" id="scaleTipPopup" role="tooltip"></span>
          </span>
          <button type="button" id="scaleLockBtn" class="scale-lock-btn active"
            onclick="toggleScaleLock()" aria-pressed="true"
            title="Diatonic Lock — auto-assign chord quality from scale">&#9654; Diatonic</button>
        </div>
      </div>

      <!-- Progression track -->
      <div class="section-label" style="margin-bottom:0.4rem">Progression</div>
      <div class="progression-track" id="progressionTrack" aria-label="Built progression" aria-live="polite">
        <span class="progression-empty" id="progEmpty">Pick a note below to start&hellip;</span>
      </div>

      <!-- Track actions -->
      <div class="track-actions">
        <div class="track-spacer"></div>
        <button class="btn-undo" onclick="builderUndo()" aria-label="Remove last item">&#8617; Undo</button>
        <button class="btn-undo" onclick="builderClear()" aria-label="Clear progression">&times; Clear</button>
      </div>

      <!-- Chord builder (chords → NNS mode) -->
      <div id="chordBuilder" style="display:none">
        <div class="palette-label">Root Note</div>
        <div class="note-palette" id="notePalette" role="group" aria-label="Root note selection"></div>
        <div class="palette-label">Quality</div>
        <div class="quality-palette" id="qualityPalette" role="group" aria-label="Chord quality selection"></div>
      </div>

      <!-- NNS builder (NNS → chords mode) -->
      <div id="nnsBuilder">
        <div class="palette-label">Scale Degree</div>
        <div class="number-palette" id="numberPalette" role="group" aria-label="Scale degree selection"></div>
        <div class="palette-label">Quality</div>
        <div class="quality-palette" id="nnsQualityPalette" role="group" aria-label="NNS chord quality selection"></div>
      </div>

    </div><!-- /panelBuilder -->

    <!-- Text panel -->
    <div id="panelText" role="tabpanel" aria-labelledby="tabText" style="display:none">
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
    </div><!-- /panelText -->

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
    <h2 class="section-label">Result</h2>
    <div class="output-wrap">
      <div class="output-box" id="outputBox" aria-live="polite">
        <span class="output-placeholder">Result will appear here&hellip;</span>
      </div>
    </div>

    <!-- Music Lab -->
    <div class="music-lab-section" id="musicLabSection">
      <div class="music-lab-header">
        <div>
          <div class="section-label">Music Lab</div>
          <h2 class="music-lab-title">Progression sketchpad and transport</h2>
          <p class="music-lab-copy">
            First expansion slice from the NAM roadmap: map the chart into bars, choose a groove,
            add a low-end guide, and audition a loop before live-input and tone-browser work lands.
          </p>
        </div>
        <div class="lab-pill-row">
          <span class="lab-pill">Pattern transport</span>
          <span class="lab-pill">Bass guide</span>
          <span class="lab-pill">Tone runway</span>
        </div>
      </div>

      <div class="music-lab-grid">
        <div class="lab-panel">
          <div class="lab-summary-grid">
            <div class="lab-stat">
              <span class="lab-stat-label">Resolved Key</span>
              <span class="lab-stat-value" id="labSummaryKey">No chart yet</span>
              <span class="lab-stat-copy" id="labSummaryKeyCopy">Convert or build a progression to anchor the loop.</span>
            </div>
            <div class="lab-stat">
              <span class="lab-stat-label">Loop Map</span>
              <span class="lab-stat-value" id="labSummaryBars">0 bars</span>
              <span class="lab-stat-copy" id="labSummaryBarsCopy">Bar and slot timing appear after planning.</span>
            </div>
            <div class="lab-stat">
              <span class="lab-stat-label">Groove</span>
              <span class="lab-stat-value" id="labSummaryGroove">Anthem Strum</span>
              <span class="lab-stat-copy" id="labSummaryGrooveCopy">Wide downbeats and anchored roots.</span>
            </div>
            <div class="lab-stat">
              <span class="lab-stat-label">Playback Path</span>
              <span class="lab-stat-value" id="labSummaryRuntime">Web Tone</span>
              <span class="lab-stat-copy" id="labSummaryRuntimeCopy">FluidSynth transport is used automatically when available.</span>
            </div>
          </div>

          <div class="lab-analysis" id="labSummaryAnalysis">
            The arrangement planner is idle. Build a chart to get section boundaries, harmonic rhythm,
            and a transport-ready loop map.
          </div>

          <div class="lab-controls-grid">
            <label class="lab-field">
              <span class="lab-field-label">Tempo</span>
              <input id="labTempo" class="lab-input" type="number" min="40" max="220" step="1" value="96" />
            </label>
            <label class="lab-field">
              <span class="lab-field-label">Meter</span>
              <select id="labMeter" class="lab-select">
                <option value="4">4/4</option>
                <option value="3">3/4</option>
                <option value="6">6/8</option>
                <option value="5">5/4</option>
              </select>
            </label>
            <label class="lab-field">
              <span class="lab-field-label">Count-In</span>
              <select id="labCountIn" class="lab-select">
                <option value="4">4 beats</option>
                <option value="2">2 beats</option>
                <option value="1">1 beat</option>
                <option value="0">None</option>
              </select>
            </label>
            <label class="lab-field">
              <span class="lab-field-label">Voicing</span>
              <select id="labVoicingStyle" class="lab-select">
                <option value="close">Close</option>
                <option value="drop2">Drop-2</option>
                <option value="drop3">Drop-3</option>
              </select>
            </label>
            <div class="lab-field">
              <span class="lab-field-label">Runtime</span>
              <div class="lab-analysis" style="margin:0">The active audio path follows the existing HQ or browser fallback stack.</div>
            </div>
          </div>

          <label class="lab-toggle" for="labVoiceLeading">
            <span>
              <span class="lab-toggle-main">Voice leading</span>
              <span class="lab-toggle-sub">Minimize note movement between consecutive chords.</span>
            </span>
            <input id="labVoiceLeading" type="checkbox" />
          </label>

          <label class="lab-toggle" for="labBassEnabled">
            <span>
              <span class="lab-toggle-main">Bass guide layer</span>
              <span class="lab-toggle-sub">Sketch the low-end before the NAM/live-input layer exists.</span>
            </span>
            <input id="labBassEnabled" type="checkbox" checked />
          </label>

          <div class="section-label" style="margin-bottom:0.5rem">Groove Presets</div>
          <div class="groove-grid" id="grooveGrid"></div>

          <div class="transport-row">
            <button class="btn-transport primary" id="arrangementBuildBtn" onclick="buildArrangement()">Build Arrangement</button>
            <button class="btn-transport secondary" id="arrangementPlayBtn" onclick="playArrangement()" disabled>Play</button>
            <button class="btn-transport ghost" id="arrangementStopBtn" onclick="stopArrangement()">Stop</button>
            <button class="btn-transport loop-toggle active" id="loopToggleBtn" onclick="toggleLoop()" title="Loop on/off" aria-pressed="true">&#x21BB; Loop</button>
            <button class="btn-transport secondary" id="arrangementExportBtn" onclick="exportMidi()" disabled>Export MIDI</button>
          </div>

          <div class="lab-transport-status" id="labTransportStatus" aria-live="polite">
            Waiting for a progression. The first implementation stage is a transport and arrangement planner on top of the current playback stack.
          </div>

          <div class="tone-library-panel">
            <div class="section-label" style="margin-bottom:0.5rem">Tone Library</div>
            <div class="lab-analysis" style="margin:0 0 0.65rem">
              Import local NAM models and optional IR files. Preview is coming in the next phase.
            </div>
            <div class="tone-library-actions">
              <button class="btn-transport secondary" id="toneImportModelBtn" onclick="openToneModelPicker()">Import Model (.nam)</button>
              <button class="btn-transport ghost" id="toneImportIrBtn" onclick="openToneIrPicker()">Import IR (.wav)</button>
              <span id="toneLibraryStatus" class="tone-library-status" aria-live="polite"></span>
            </div>
            <input id="toneModelInput" type="file" accept=".nam,application/json" style="display:none" />
            <input id="toneIrInput" type="file" accept=".wav,audio/wav" style="display:none" />
            <div id="toneLibraryList" class="tone-library-list" aria-live="polite">
              <div class="arrangement-placeholder">
                <strong>No tones imported yet.</strong>
                <span>Bring in a `.nam` model to start building your local tone slot list.</span>
              </div>
            </div>
          </div>
        </div>

        <div class="lab-panel timeline-shell">
          <div class="section-label" style="margin-bottom:0.5rem">Arrangement Timeline</div>
          <div id="arrangementTimeline" aria-live="polite">
            <div class="arrangement-placeholder">
              <strong>Build the first loop.</strong>
              <span>The planner will resolve a key, split the progression into bars, and expose each chord slot as a playable timeline cell.</span>
            </div>
          </div>

          <div class="section-label" style="margin:1rem 0 0.5rem">Expansion Runway</div>
          <div class="runway-grid">
            <div class="runway-card">
              <span class="runway-label">Live Input <span class="runway-badge">Coming Soon</span></span>
              <span class="runway-title">Practice Rig</span>
              <span class="runway-copy">Use the same chart and fretboard targets as the future monitoring surface for real guitar or bass input.</span>
            </div>
            <div class="runway-card">
              <span class="runway-label">Tone Browser <span class="runway-badge">Coming Soon</span></span>
              <span class="runway-title">Tone Slots</span>
              <span class="runway-copy">This transport is the place to hang starter tones, user-imported NAM captures, and section-specific tone swaps.</span>
            </div>
            <div class="runway-card">
              <span class="runway-label">Export</span>
              <span class="runway-title">MIDI Hand-Off</span>
              <span class="runway-copy">Export the current arrangement as a Standard MIDI File. Stem export and re-amp workflows are planned for a future update.</span>
            </div>
          </div>
        </div>
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
          <button class="fb-filter-chip active" data-degree="1" aria-pressed="true" aria-label="Toggle degree 1" onclick="toggleDegree(1)">1</button>
          <button class="fb-filter-chip active" data-degree="2" aria-pressed="true" aria-label="Toggle degree 2" onclick="toggleDegree(2)">2</button>
          <button class="fb-filter-chip active" data-degree="3" aria-pressed="true" aria-label="Toggle degree 3" onclick="toggleDegree(3)">3</button>
          <button class="fb-filter-chip active" data-degree="4" aria-pressed="true" aria-label="Toggle degree 4" onclick="toggleDegree(4)">4</button>
          <button class="fb-filter-chip active" data-degree="5" aria-pressed="true" aria-label="Toggle degree 5" onclick="toggleDegree(5)">5</button>
          <button class="fb-filter-chip active" data-degree="6" aria-pressed="true" aria-label="Toggle degree 6" onclick="toggleDegree(6)">6</button>
          <button class="fb-filter-chip active" data-degree="7" aria-pressed="true" aria-label="Toggle degree 7" onclick="toggleDegree(7)">7</button>
          <button class="fb-filter-chip preset" aria-label="Show degrees 1, 3, and 6 only" onclick="applyPreset([1,3,6])">1-3-6</button>
        </div>

        <div class="audio-status">
          <span id="audioStatusPill" class="audio-status-pill warn" aria-live="polite">Web Tone Fallback</span>
          <span id="audioStatusDetail" class="audio-status-detail" aria-live="polite"></span>
          <div id="runtimeProgressWrap" class="audio-progress-wrap" style="display:none" aria-live="polite" aria-label="Installation progress">
            <div class="audio-progress-track">
              <div id="runtimeProgressFill" class="audio-progress-fill"></div>
            </div>
            <span id="runtimeProgressLabel" class="audio-progress-label">Starting…</span>
          </div>
          <button id="audioRuntimeInstallBtn" class="audio-install-btn" onclick="installRuntime()" style="display:none">
            Install FluidSynth
          </button>
          <button id="audioInstallBtn" class="audio-install-btn" onclick="installDefaultPack()" style="display:none">
            Install Free HQ Pack
          </button>
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

  </div><!-- /workspace -->

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
    switchInputTab('text');
    document.getElementById('inputArea').value = ex.text;
    doConvert();
  });
  grid.appendChild(chip);
});

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function appFetch(resource, options = {}) {
  const headers = new Headers(options.headers || {});
  return fetch(resource, { credentials: 'same-origin', ...options, headers });
}

const MUSIC_LAB_GROOVES = {
  anthem: {
    id: 'anthem',
    name: 'Anthem Strum',
    description: 'Wide downbeats with anchored root pulses.',
    chordStyle: 'strum',
    strumMs: 24,
    gate: 0.86,
    bassPattern: 'downbeat-octave'
  },
  pulse: {
    id: 'pulse',
    name: 'Pulse Grid',
    description: 'Block hits that keep every slot moving.',
    chordStyle: 'block',
    strumMs: 0,
    gate: 0.66,
    bassPattern: 'slot-roots'
  },
  lantern: {
    id: 'lantern',
    name: 'Lantern Pick',
    description: 'Short picked stabs with a lighter bass bed.',
    chordStyle: 'strum',
    strumMs: 16,
    gate: 0.52,
    bassPattern: 'half-time'
  },
  pads: {
    id: 'pads',
    name: 'Cinema Pads',
    description: 'Held chords for larger arrangement sketches.',
    chordStyle: 'block',
    strumMs: 0,
    gate: 1.0,
    bassPattern: 'bar-root'
  },
  waltz: {
    id: 'waltz',
    name: 'Waltz',
    description: 'Classic 3/4 feel with strong downbeat and lighter beats 2-3.',
    chordStyle: 'strum',
    strumMs: 20,
    gate: 0.75,
    bassPattern: 'slot-roots'
  },
  shuffle: {
    id: 'shuffle',
    name: 'Shuffle',
    description: 'Swung eighth-note groove with a loose feel.',
    chordStyle: 'strum',
    strumMs: 18,
    gate: 0.7,
    bassPattern: 'slot-roots'
  },
  funk: {
    id: 'funk',
    name: 'Funk Grid',
    description: 'Syncopated staccato hits with offbeat emphasis.',
    chordStyle: 'block',
    strumMs: 0,
    gate: 0.4,
    bassPattern: 'slot-roots'
  },
  reggae: {
    id: 'reggae',
    name: 'Reggae Skank',
    description: 'Offbeat chord stabs with a steady bass anchor.',
    chordStyle: 'block',
    strumMs: 0,
    gate: 0.35,
    bassPattern: 'slot-roots'
  },
  ballad: {
    id: 'ballad',
    name: 'Ballad',
    description: 'Wide sustained strums for slow, expressive arrangements.',
    chordStyle: 'strum',
    strumMs: 30,
    gate: 0.95,
    bassPattern: 'slot-roots'
  }
};

let audioState = {
  hq_ready: false,
  engine: 'unavailable',
  reason: 'init_error',
  fallback: 'web_tone',
  pack: { id: 'fluidr3_gm', installed: false, path: null },
  message: ''
};
let installInProgress = false;
let defaultInstallJobId = '';
let musicLabState = {
  selectedGroove: 'anthem',
  plan: null,
  playTimers: [],
  isPlaying: false,
  loopEnabled: true,
  activeSlotKey: '',
  lastBuiltInput: ''
};
let toneLibraryState = {
  tones: [],
  irs: [],
  pendingToneForIr: null
};

const webTone = (() => {
  let ctx = null;
  const voices = new Map();

  function ensureCtx() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  function midiToFreq(midi) {
    return 440 * Math.pow(2, (midi - 69) / 12);
  }

  function noteOn(midi, velocity = 96) {
    const audioCtx = ensureCtx();
    const now = audioCtx.currentTime;
    const key = String(midi);
    if (voices.has(key)) {
      noteOff(midi);
    }

    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    const tone = audioCtx.createOscillator();
    const toneGain = audioCtx.createGain();

    osc.type = 'triangle';
    osc.frequency.setValueAtTime(midiToFreq(midi), now);
    tone.type = 'sine';
    tone.frequency.setValueAtTime(midiToFreq(midi) * 2, now);

    const peak = Math.max(0.05, Math.min(0.45, velocity / 255));
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(peak, now + 0.012);
    gain.gain.exponentialRampToValueAtTime(peak * 0.68, now + 0.09);

    toneGain.gain.setValueAtTime(0.0001, now);
    toneGain.gain.exponentialRampToValueAtTime(peak * 0.18, now + 0.02);
    toneGain.gain.exponentialRampToValueAtTime(peak * 0.08, now + 0.1);

    osc.connect(gain).connect(audioCtx.destination);
    tone.connect(toneGain).connect(audioCtx.destination);
    osc.start(now);
    tone.start(now);

    voices.set(key, { osc, tone, gain, toneGain });
  }

  function noteOff(midi) {
    const voice = voices.get(String(midi));
    if (!voice || !ctx) return;
    const now = ctx.currentTime;
    voice.gain.gain.cancelScheduledValues(now);
    voice.toneGain.gain.cancelScheduledValues(now);
    voice.gain.gain.setValueAtTime(Math.max(0.0001, voice.gain.gain.value), now);
    voice.toneGain.gain.setValueAtTime(Math.max(0.0001, voice.toneGain.gain.value), now);
    voice.gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
    voice.toneGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
    voice.osc.stop(now + 0.2);
    voice.tone.stop(now + 0.2);
    voices.delete(String(midi));
  }

  function playNote(midi, velocity = 96, durationMs = 450) {
    noteOn(midi, velocity);
    window.setTimeout(() => noteOff(midi), durationMs);
  }

  function playChord(midis, style = 'strum', strumMs = 28, noteMs = 700, velocity = 96) {
    midis.forEach((midi, idx) => {
      const delay = style === 'strum' ? idx * strumMs : 0;
      window.setTimeout(() => playNote(midi, velocity, noteMs), delay);
    });
  }

  function panic() {
    Array.from(voices.keys()).forEach(key => noteOff(parseInt(key, 10)));
  }

  return { noteOn, noteOff, playNote, playChord, panic };
})();

function _setAudioState(nextState) {
  audioState = {
    hq_ready: !!nextState.hq_ready,
    hq_requested: nextState.hq_requested !== false,
    engine: nextState.engine || 'unavailable',
    reason: nextState.reason || 'init_error',
    fallback: nextState.fallback || 'web_tone',
    fallback_active: nextState.fallback_active !== false,
    last_install_error: nextState.last_install_error || '',
    scheduler: nextState.scheduler || {},
    pack: nextState.pack || { id: 'fluidr3_gm', installed: false, path: null },
    message: nextState.message || ''
  };
  updateAudioStatusUI();
}

function updateAudioStatusUI() {
  const pill = document.getElementById('audioStatusPill');
  const detail = document.getElementById('audioStatusDetail');
  const installBtn = document.getElementById('audioInstallBtn');
  const runtimeBtn = document.getElementById('audioRuntimeInstallBtn');
  if (!pill || !detail || !installBtn || !runtimeBtn) return;

  pill.classList.remove('ready', 'warn');

  if (audioState.hq_ready) {
    pill.classList.add('ready');
    pill.textContent = 'HQ Ready';
    detail.textContent = audioState.message || 'FluidSynth engine is active.';
    installBtn.style.display = 'none';
    runtimeBtn.style.display = 'none';
    return;
  }

  pill.classList.add('warn');
  if (audioState.reason === 'missing_soundfont') {
    pill.textContent = 'HQ Missing • Web Tone Fallback';
  } else if (audioState.reason === 'missing_fluidsynth') {
    pill.textContent = 'FluidSynth Missing • Web Tone Fallback';
  } else if (audioState.reason === 'disabled') {
    pill.textContent = 'Audio Disabled';
  } else {
    pill.textContent = 'Web Tone Fallback';
  }

  if (audioState.message) {
    detail.textContent = audioState.message;
  } else if (audioState.last_install_error) {
    detail.textContent = audioState.last_install_error;
  } else if (audioState.reason === 'missing_soundfont') {
    detail.textContent = 'Install the free HQ pack to enable FluidSynth playback.';
  } else if (audioState.reason === 'missing_fluidsynth') {
    detail.textContent = 'Install the FluidSynth runtime. The app can bootstrap a portable copy on Windows.';
  } else if (audioState.reason === 'disabled') {
    detail.textContent = 'Audio is disabled in the local configuration.';
  } else {
    detail.textContent = 'Browser tone preview remains available.';
  }

  installBtn.style.display = audioState.reason === 'missing_soundfont' ? '' : 'none';
  runtimeBtn.style.display = audioState.reason === 'missing_fluidsynth' ? '' : 'none';
  refreshMusicLabRuntimeSummary();
}

async function refreshAudioStatus() {
  try {
    const response = await appFetch('/audio/status');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'status failed');
    _setAudioState(payload);
  } catch (_err) {
    _setAudioState({ hq_ready: false, engine: 'unavailable', reason: 'init_error', fallback: 'web_tone', pack: { id: 'fluidr3_gm', installed: false, path: null } });
  }
}

async function installDefaultPack() {
  if (installInProgress) return;
  const btn = document.getElementById('audioInstallBtn');
  if (!btn) return;
  installInProgress = true;
  btn.classList.add('loading');
  try {
    const response = await appFetch('/audio/install-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    });
    const payload = await response.json();
    if (!response.ok || !payload.started) {
      if (payload && payload.reason) {
        _setAudioState({
          hq_ready: false,
          engine: 'unavailable',
          reason: payload.reason,
          fallback: 'web_tone',
          pack: audioState.pack,
          message: payload.error || 'Failed to install the default pack.'
        });
      }
      return;
    }
    defaultInstallJobId = payload.job && payload.job.id ? payload.job.id : '';
    _pollDefaultInstall();
  } catch (_err) {
    _setAudioState({
      hq_ready: false,
      engine: 'unavailable',
      reason: 'init_error',
      fallback: 'web_tone',
      pack: audioState.pack,
      message: 'Failed to contact the local audio installer.'
    });
  } finally {
    btn.classList.remove('loading');
    installInProgress = false;
  }
}

function _pollDefaultInstall() {
  window.setTimeout(async () => {
    try {
      const resp = await appFetch('/audio/install-default/status');
      const job = await resp.json();
      if (job.running) {
        _pollDefaultInstall();
        return;
      }
      if (job.result) {
        _setAudioState({ ...(job.result.audio_status || job.result), message: 'Free HQ pack installed.' });
        return;
      }
      if (job.error) {
        _setAudioState({ ...audioState, message: job.error });
      }
    } catch (_err) {
      _setAudioState({ ...audioState, message: 'Failed to poll pack installer.' });
    } finally {
      installInProgress = false;
      const btn = document.getElementById('audioInstallBtn');
      if (btn) btn.classList.remove('loading');
    }
  }, 600);
}

let runtimeInstallInProgress = false;
let _runtimePollTimer = null;

function _updateRuntimeProgress(pct, stage) {
  const fill = document.getElementById('runtimeProgressFill');
  const label = document.getElementById('runtimeProgressLabel');
  if (fill) fill.style.width = Math.min(100, Math.max(0, pct)) + '%';
  if (label) label.textContent = stage || '';
}

function _runtimeInstallFinished(result, error) {
  clearTimeout(_runtimePollTimer);
  runtimeInstallInProgress = false;
  const progressWrap = document.getElementById('runtimeProgressWrap');
  if (progressWrap) progressWrap.style.display = 'none';
  if (result && result.audio_status) {
    _setAudioState({
      ...result.audio_status,
      message: result.message || ''
    });
    return;
  }
  _setAudioState({
    ...audioState,
    message: error || 'FluidSynth installation did not complete.'
  });
}

function _pollRuntimeInstall() {
  _runtimePollTimer = window.setTimeout(async () => {
    try {
      const resp = await appFetch('/audio/install-runtime/status');
      const job = await resp.json();
      _updateRuntimeProgress(job.pct || 0, job.stage || '');
      if (job.running) {
        _pollRuntimeInstall();
      } else {
        _runtimeInstallFinished(job.result, job.error);
      }
    } catch (_err) {
      _runtimeInstallFinished(null, 'Polling error');
    }
  }, 800);
}

async function installRuntime() {
  if (runtimeInstallInProgress) return;
  const btn = document.getElementById('audioRuntimeInstallBtn');
  const progressWrap = document.getElementById('runtimeProgressWrap');
  if (!btn || !progressWrap) return;

  runtimeInstallInProgress = true;
  btn.style.display = 'none';
  progressWrap.style.display = 'flex';
  _updateRuntimeProgress(0, 'Starting…');

  try {
    const response = await appFetch('/audio/install-runtime', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    });
    const payload = await response.json();
    if (!response.ok || !payload.started) {
      _runtimeInstallFinished(null, payload.reason || 'Failed to start');
      return;
    }
    _pollRuntimeInstall();
  } catch (_err) {
    _runtimeInstallFinished(null, 'Network error');
  }
}

async function _postAudio(endpoint, payload) {
  try {
    const response = await appFetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const body = await response.json();
    if (response.status === 409) {
      _setAudioState({
        hq_ready: false,
        engine: 'unavailable',
        reason: body.reason || 'init_error',
        fallback: 'web_tone',
        pack: audioState.pack,
        message: body.error || ''
      });
      return false;
    }
    if (!response.ok) return false;
    if (body.status) _setAudioState(body.status);
    return true;
  } catch (_err) {
    _setAudioState({
      hq_ready: false,
      engine: 'unavailable',
      reason: 'init_error',
      fallback: 'web_tone',
      pack: audioState.pack
    });
    return false;
  }
}

async function playNotePreview(midi, velocity = 96, durationMs = 450, channel = 0) {
  const ok = audioState.hq_ready
    ? await _postAudio('/audio/play-note', { midi, velocity, duration_ms: durationMs, channel })
    : false;
  if (!ok) webTone.playNote(midi, velocity, durationMs);
}

async function noteOnPreview(midi, velocity = 96, channel = 0) {
  const ok = audioState.hq_ready
    ? await _postAudio('/audio/note-on', { midi, velocity, channel })
    : false;
  if (!ok) webTone.noteOn(midi, velocity);
}

async function noteOffPreview(midi, channel = 0) {
  const ok = audioState.hq_ready
    ? await _postAudio('/audio/note-off', { midi, channel })
    : false;
  if (!ok) webTone.noteOff(midi);
}

async function playChordPreview(midis, style = 'strum', strumMs = 28, noteMs = 700, velocity = 96, channel = 0) {
  const ok = audioState.hq_ready
    ? await _postAudio('/audio/play-chord', { midis, style, strum_ms: strumMs, note_ms: noteMs, velocity, channel })
    : false;
  if (!ok) webTone.playChord(midis, style, strumMs, noteMs, velocity);
}

function panicAudio() {
  webTone.panic();
  if (audioState.hq_ready) _postAudio('/audio/panic', {});
}

function getCurrentInputText() {
  const builderPanel = document.getElementById('panelBuilder');
  return (builderPanel && builderPanel.style.display !== 'none')
    ? buildProgressionString()
    : document.getElementById('inputArea').value.trim();
}

function getMusicLabGroove(grooveId = musicLabState.selectedGroove) {
  return MUSIC_LAB_GROOVES[grooveId] || MUSIC_LAB_GROOVES.anthem;
}

function setTransportStatus(message, mode = '') {
  const status = document.getElementById('labTransportStatus');
  if (!status) return;
  status.textContent = message;
  status.classList.remove('ready', 'warn', 'busy');
  if (mode) status.classList.add(mode);
}

function syncArrangementButtons() {
  const playBtn = document.getElementById('arrangementPlayBtn');
  const stopBtn = document.getElementById('arrangementStopBtn');
  const exportBtn = document.getElementById('arrangementExportBtn');
  if (playBtn) {
    playBtn.disabled = !musicLabState.plan;
    playBtn.title = playBtn.disabled ? 'Build an arrangement first' : '';
  }
  if (stopBtn) {
    stopBtn.disabled = !musicLabState.isPlaying;
    stopBtn.title = stopBtn.disabled ? 'Transport is stopped' : '';
  }
  if (exportBtn) {
    exportBtn.disabled = !musicLabState.plan;
    exportBtn.title = exportBtn.disabled ? 'Build an arrangement first' : '';
  }
}

function refreshMusicLabRuntimeSummary() {
  const runtimeValue = document.getElementById('labSummaryRuntime');
  const runtimeCopy = document.getElementById('labSummaryRuntimeCopy');
  if (!runtimeValue || !runtimeCopy) return;

  if (audioState.hq_ready) {
    runtimeValue.textContent = 'HQ Ready';
    runtimeCopy.textContent = 'Sequence transport will use the FluidSynth backend.';
    return;
  }

  if (audioState.reason === 'missing_fluidsynth') {
    runtimeValue.textContent = 'Runtime Missing';
    runtimeCopy.textContent = 'Browser transport is active until the FluidSynth runtime is installed.';
    return;
  }

  if (audioState.reason === 'missing_soundfont') {
    runtimeValue.textContent = 'HQ Pack Missing';
    runtimeCopy.textContent = 'Install the free pack to hand the full loop to the backend.';
    return;
  }

  runtimeValue.textContent = 'Web Tone';
  runtimeCopy.textContent = 'Browser transport stays available when HQ playback is unavailable.';
}

function syncMusicLabSummary(plan = musicLabState.plan) {
  const keyValue = document.getElementById('labSummaryKey');
  const keyCopy = document.getElementById('labSummaryKeyCopy');
  const barsValue = document.getElementById('labSummaryBars');
  const barsCopy = document.getElementById('labSummaryBarsCopy');
  const grooveValue = document.getElementById('labSummaryGroove');
  const grooveCopy = document.getElementById('labSummaryGrooveCopy');
  const analysis = document.getElementById('labSummaryAnalysis');

  if (!keyValue || !keyCopy || !barsValue || !barsCopy || !grooveValue || !grooveCopy || !analysis) return;

  const groove = getMusicLabGroove();
  grooveValue.textContent = groove.name;
  grooveCopy.textContent = groove.description;
  refreshMusicLabRuntimeSummary();

  if (!plan) {
    keyValue.textContent = 'No chart yet';
    keyCopy.textContent = 'Convert or build a progression to anchor the loop.';
    barsValue.textContent = '0 bars';
    barsCopy.textContent = 'Bar and slot timing appear after planning.';
    analysis.textContent = 'The arrangement planner is idle. Build a chart to get section boundaries, harmonic rhythm, and a transport-ready loop map.';
    syncArrangementButtons();
    return;
  }

  keyValue.textContent = `${plan.resolved_key.tonic} ${plan.resolved_key.mode}`;
  keyCopy.textContent = plan.analysis.resolved_via === 'best_guess'
    ? 'Using the strongest inferred interpretation for the current chart.'
    : plan.analysis.key_changes > 0
      ? 'The chart includes section-level key changes.'
      : 'Key came from the chart or the strongest explicit interpretation.';
  barsValue.textContent = `${plan.summary.bar_count} bars / ${plan.summary.slot_count} slots`;
  barsCopy.textContent = `${plan.meter_label} at ${plan.tempo} BPM with ${plan.count_in_beats} count-in beats.`;
  analysis.textContent = plan.analysis.resolved_via === 'section_inference'
    ? 'Sections were split by sustained key movement. Each lane below keeps its own harmonic center so later live-input and tone routing can follow the chart.'
    : 'This first slice builds a playable transport lane on top of the existing converter and audio stack. Later NAM, live-input, and export features can attach to the same bar map.';
  syncArrangementButtons();
}

function clearArrangementTimeline(title, body) {
  const timeline = document.getElementById('arrangementTimeline');
  if (!timeline) return;
  timeline.innerHTML = `
    <div class="arrangement-placeholder">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(body)}</span>
    </div>
  `;
}

function renderGrooveOptions() {
  const grid = document.getElementById('grooveGrid');
  if (!grid) return;
  grid.innerHTML = '';

  Object.values(MUSIC_LAB_GROOVES).forEach(groove => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'groove-card' + (musicLabState.selectedGroove === groove.id ? ' active' : '');
    button.setAttribute('aria-pressed', musicLabState.selectedGroove === groove.id ? 'true' : 'false');
    button.addEventListener('click', () => setMusicLabGroove(groove.id));

    const name = document.createElement('span');
    name.className = 'groove-name';
    name.textContent = groove.name;

    const copy = document.createElement('span');
    copy.className = 'groove-copy';
    copy.textContent = groove.description;

    button.appendChild(name);
    button.appendChild(copy);
    grid.appendChild(button);
  });
}

function setMusicLabGroove(grooveId) {
  musicLabState.selectedGroove = MUSIC_LAB_GROOVES[grooveId] ? grooveId : 'anthem';
  if (musicLabState.plan) {
    musicLabState.plan.groove = getMusicLabGroove();
  }
  renderGrooveOptions();
  syncMusicLabSummary();
}

function getPlanSlot(sectionIndex, barIndex, slotIndex) {
  if (!musicLabState.plan) return null;
  const section = musicLabState.plan.sections[sectionIndex];
  if (!section) return null;
  const bar = section.bars[barIndex];
  if (!bar) return null;
  return bar.slots[slotIndex] || null;
}

function slotKeyFromIndexes(sectionIndex, barIndex, slotIndex) {
  return `${sectionIndex}:${barIndex}:${slotIndex}`;
}

function selectArrangementSlot(slotKey, playing = false) {
  document.querySelectorAll('.timeline-slot').forEach(node => {
    const isActive = node.dataset.slotKey === slotKey;
    node.classList.toggle('active', isActive);
    node.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    if (!isActive && !playing) node.classList.remove('is-playing');
  });
  musicLabState.activeSlotKey = slotKey;
}

function setArrangementPlayingSlot(slotKey, enabled) {
  const node = document.querySelector(`.timeline-slot[data-slot-key="${slotKey}"]`);
  if (!node) return;
  node.classList.toggle('is-playing', enabled);
  if (enabled) selectArrangementSlot(slotKey, true);
}

function slotToChordData(slot) {
  return {
    type: 'chord',
    text: slot.chord,
    root: extractChordRoot(slot.chord),
    keyTonic: slot.key.tonic,
    keyMode: slot.key.mode
  };
}

function extractChordRoot(text) {
  const match = String(text || '').match(/^[A-G](?:#|b)?/);
  return match ? match[0] : null;
}

function renderArrangementTimeline() {
  const timeline = document.getElementById('arrangementTimeline');
  if (!timeline) return;

  if (!musicLabState.plan) {
    clearArrangementTimeline(
      'Build the first loop.',
      'The planner will resolve a key, split the progression into bars, and expose each chord slot as a playable timeline cell.'
    );
    return;
  }

  timeline.innerHTML = '';
  const sectionsWrap = document.createElement('div');
  sectionsWrap.className = 'arrangement-sections';

  musicLabState.plan.sections.forEach((section, sectionIndex) => {
    const sectionNode = document.createElement('div');
    sectionNode.className = 'timeline-section';

    const head = document.createElement('div');
    head.className = 'timeline-section-head';

    const title = document.createElement('div');
    title.className = 'timeline-section-title';
    title.textContent = `${section.label} • ${section.key.tonic} ${section.key.mode}`;

    const copy = document.createElement('div');
    copy.className = 'timeline-section-copy';
    copy.textContent = section.analysis === 'section_inference'
      ? 'Key-shifted lane'
      : section.preview;

    head.appendChild(title);
    head.appendChild(copy);
    sectionNode.appendChild(head);

    const barsWrap = document.createElement('div');
    barsWrap.className = 'timeline-bars';

    section.bars.forEach((bar, barIndex) => {
      const barNode = document.createElement('article');
      barNode.className = 'timeline-bar';

      const top = document.createElement('div');
      top.className = 'timeline-bar-top';

      const label = document.createElement('div');
      label.className = 'timeline-bar-label';
      label.textContent = `${bar.label} • ${bar.beats} beats`;

      const preview = document.createElement('div');
      preview.className = 'timeline-bar-preview';
      preview.textContent = bar.preview;

      top.appendChild(label);
      top.appendChild(preview);
      barNode.appendChild(top);

      const slotRow = document.createElement('div');
      slotRow.className = 'timeline-slot-row';
      slotRow.style.gridTemplateColumns = `repeat(${Math.max(1, bar.slots.length)}, minmax(0, 1fr))`;

      bar.slots.forEach((slot, slotIndex) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'timeline-slot';
        button.setAttribute('aria-pressed', 'false');
        button.dataset.slotKey = slotKeyFromIndexes(sectionIndex, barIndex, slotIndex);
        button.addEventListener('click', () => previewArrangementSlot(sectionIndex, barIndex, slotIndex));

        const topLine = document.createElement('div');
        topLine.className = 'timeline-slot-top';

        const chord = document.createElement('span');
        chord.className = 'timeline-slot-chord';
        chord.textContent = slot.chord;

        const timing = document.createElement('span');
        timing.className = 'timeline-slot-timing';
        timing.textContent = `${slot.beat_duration} beats`;

        topLine.appendChild(chord);
        topLine.appendChild(timing);

        const sub = document.createElement('div');
        sub.className = 'timeline-slot-sub';
        const nns = document.createElement('span');
        nns.textContent = slot.nns || 'Chord input';
        const key = document.createElement('span');
        key.textContent = `${slot.key.tonic} ${slot.key.mode}`;
        sub.appendChild(nns);
        sub.appendChild(key);

        button.appendChild(topLine);
        button.appendChild(sub);
        slotRow.appendChild(button);
      });

      barNode.appendChild(slotRow);
      barsWrap.appendChild(barNode);
    });

    sectionNode.appendChild(barsWrap);
    sectionsWrap.appendChild(sectionNode);
  });

  timeline.appendChild(sectionsWrap);

  if (musicLabState.activeSlotKey) {
    selectArrangementSlot(musicLabState.activeSlotKey);
  }
}

async function buildArrangement(options = {}) {
  const input = getCurrentInputText();
  if (!input) {
    stopArrangement({ silent: true });
    musicLabState.plan = null;
    musicLabState.lastBuiltInput = '';
    musicLabState.activeSlotKey = '';
    syncMusicLabSummary();
    clearArrangementTimeline(
      'Build the first loop.',
      'Add a chart in Builder or Text mode to map bars, slot timing, and transport playback.'
    );
    setTransportStatus('Add a progression first.', 'warn');
    return null;
  }

  stopArrangement({ silent: true });
  const buildBtn = document.getElementById('arrangementBuildBtn');
  if (buildBtn) buildBtn.disabled = true;
  if (!options.silent) setTransportStatus('Building arrangement...', 'busy');

  const payload = {
    input,
    tempo: parseInt(document.getElementById('labTempo').value || '96', 10),
    meter: parseInt(document.getElementById('labMeter').value || '4', 10),
    groove: musicLabState.selectedGroove,
    count_in_beats: parseInt(document.getElementById('labCountIn').value || '4', 10),
    bass_enabled: !!document.getElementById('labBassEnabled').checked,
    voicing_style: document.getElementById('labVoicingStyle').value || 'close',
    voice_leading: !!document.getElementById('labVoiceLeading').checked
  };

  try {
    const response = await appFetch('/arrangement/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || 'Arrangement planning failed');

    musicLabState.plan = body.plan;
    musicLabState.plan.groove = getMusicLabGroove(body.plan.groove && body.plan.groove.id);
    musicLabState.selectedGroove = musicLabState.plan.groove.id;
    musicLabState.lastBuiltInput = input;
    renderGrooveOptions();
    syncMusicLabSummary();
    renderArrangementTimeline();
    setTransportStatus(
      options.silent
        ? 'Arrangement synced from the current chart. Press Play Loop to audition it.'
        : 'Arrangement ready. Press Play Loop to audition it.',
      'ready'
    );
    return musicLabState.plan;
  } catch (err) {
    musicLabState.plan = null;
    musicLabState.activeSlotKey = '';
    syncMusicLabSummary();
    clearArrangementTimeline(
      'Arrangement planning failed.',
      String(err && err.message ? err.message : err)
    );
    setTransportStatus(String(err && err.message ? err.message : err), 'warn');
    return null;
  } finally {
    if (buildBtn) buildBtn.disabled = false;
    syncArrangementButtons();
  }
}

function previewArrangementSlot(sectionIndex, barIndex, slotIndex) {
  const slot = getPlanSlot(sectionIndex, barIndex, slotIndex);
  if (!slot) return;

  const slotKey = slotKeyFromIndexes(sectionIndex, barIndex, slotIndex);
  selectArrangementSlot(slotKey);
  const chordData = slotToChordData(slot);
  focusMusicalObject(chordData);
  const midis = getChordMidiNotes(chordData, { tonic: slot.key.tonic, mode: slot.key.mode });
  if (midis.length > 0) {
    playChordPreview(midis, 'strum', 24, 760, 96, 0);
  }
}

function getChordBassValue(chord, key) {
  const slash = String(chord.text || '').match(/\/([A-G](?:#|b)?)/);
  if (slash) return getNoteValue(slash[1]);
  return getChordRootValue(chord, key);
}

function getBassMidi(chord, key) {
  let midi = 36 + getChordBassValue(chord, key);
  while (midi > 52) midi -= 12;
  while (midi < 28) midi += 12;
  return midi;
}

function addBassEventsForSlot(events, slot, chordData, groove, startMs, beatMs) {
  const key = { tonic: chordData.keyTonic, mode: chordData.keyMode };
  const bassMidi = getBassMidi(chordData, key);
  const shortMs = Math.max(140, Math.round(Math.min(slot.beat_duration * beatMs * 0.48, 340)));

  if (groove.bassPattern === 'bar-root' && slot.beat_start !== 0) return;
  if (groove.bassPattern === 'half-time' && slot.beat_start !== 0) return;

  events.push({
    kind: 'note',
    delay_ms: startMs,
    duration_ms: shortMs,
    velocity: 86,
    channel: 1,
    midi: bassMidi
  });

  if (groove.bassPattern === 'downbeat-octave' && slot.beat_duration >= 2) {
    events.push({
      kind: 'note',
      delay_ms: startMs + Math.round(beatMs * Math.min(2, slot.beat_duration / 2)),
      duration_ms: shortMs,
      velocity: 78,
      channel: 1,
      midi: Math.min(76, bassMidi + 12)
    });
  }
}

function buildArrangementSequence(plan) {
  const groove = getMusicLabGroove(plan.groove && plan.groove.id);
  const beatMs = 60000 / plan.tempo;
  const events = [];
  const highlights = [];

  for (let beat = 0; beat < plan.count_in_beats; beat++) {
    events.push({
      kind: 'note',
      delay_ms: Math.round(beat * beatMs),
      duration_ms: 140,
      velocity: beat === plan.count_in_beats - 1 ? 118 : 92,
      channel: 0,
      midi: beat === plan.count_in_beats - 1 ? 84 : 79
    });
  }

  let cursorBeats = plan.count_in_beats;
  plan.sections.forEach((section, sectionIndex) => {
    section.bars.forEach((bar, barIndex) => {
      const barStartBeats = cursorBeats;
      bar.slots.forEach((slot, slotIndex) => {
        const chordData = slotToChordData(slot);
        const key = { tonic: slot.key.tonic, mode: slot.key.mode };
        const midis = getChordMidiNotes(chordData, key);
        if (midis.length === 0) return;

        const startMs = Math.round((barStartBeats + slot.beat_start) * beatMs);
        const durationMs = Math.max(180, Math.round(slot.beat_duration * beatMs * groove.gate));
        events.push({
          kind: 'chord',
          delay_ms: startMs,
          duration_ms: durationMs,
          velocity: groove.id === 'lantern' ? 82 : 96,
          channel: 0,
          midis,
          style: groove.chordStyle,
          strum_ms: groove.strumMs
        });

        if (plan.bass_enabled) {
          addBassEventsForSlot(events, slot, chordData, groove, startMs, beatMs);
        }

        highlights.push({
          key: slotKeyFromIndexes(sectionIndex, barIndex, slotIndex),
          delay_ms: startMs,
          duration_ms: Math.max(220, durationMs)
        });
      });
      cursorBeats += bar.beats;
    });
  });

  return {
    events,
    highlights,
    totalMs: Math.round((cursorBeats * beatMs) + 240)
  };
}

function queueLocalSequence(events) {
  events.forEach(event => {
    const timer = window.setTimeout(() => {
      if (event.kind === 'note') {
        webTone.playNote(event.midi, event.velocity, event.duration_ms);
        return;
      }
      webTone.playChord(event.midis, event.style, event.strum_ms || 0, event.duration_ms, event.velocity);
    }, event.delay_ms);
    musicLabState.playTimers.push(timer);
  });
}

function finishArrangementPlayback() {
  if (!musicLabState.isPlaying) return;
  if (musicLabState.loopEnabled && musicLabState.plan) {
    // Re-trigger playback for continuous looping
    musicLabState.playTimers.forEach(timer => window.clearTimeout(timer));
    musicLabState.playTimers = [];
    document.querySelectorAll('.timeline-slot.is-playing').forEach(node => node.classList.remove('is-playing'));
    _startArrangementPlayback(musicLabState.plan);
    return;
  }
  musicLabState.isPlaying = false;
  document.querySelectorAll('.timeline-slot.is-playing').forEach(node => node.classList.remove('is-playing'));
  syncArrangementButtons();
  setTransportStatus('Playback finished.', 'ready');
}

function scheduleArrangementHighlights(highlights, totalMs) {
  highlights.forEach(item => {
    musicLabState.playTimers.push(window.setTimeout(() => {
      setArrangementPlayingSlot(item.key, true);
    }, item.delay_ms));
    musicLabState.playTimers.push(window.setTimeout(() => {
      setArrangementPlayingSlot(item.key, false);
    }, item.delay_ms + item.duration_ms));
  });

  musicLabState.playTimers.push(window.setTimeout(() => {
    finishArrangementPlayback();
  }, totalMs));
}

async function _startArrangementPlayback(plan) {
  const sequence = buildArrangementSequence(plan);
  if (sequence.events.length === 0) {
    setTransportStatus('No playable chord data was found in the current chart.', 'warn');
    musicLabState.isPlaying = false;
    syncArrangementButtons();
    return;
  }

  scheduleArrangementHighlights(sequence.highlights, sequence.totalMs);

  let usedBackend = false;
  if (audioState.hq_ready) {
    usedBackend = await _postAudio('/audio/play-sequence', {
      events: sequence.events,
      reset: true
    });
  }

  if (!usedBackend) {
    queueLocalSequence(sequence.events);
    setTransportStatus(
      musicLabState.loopEnabled ? 'Looping\u2026' : 'Playing\u2026',
      'busy'
    );
    return;
  }

  setTransportStatus(
    musicLabState.loopEnabled ? 'Looping via FluidSynth\u2026' : 'Playing via FluidSynth\u2026',
    'busy'
  );
}

async function playArrangement() {
  let plan = musicLabState.plan;
  if (!plan || musicLabState.lastBuiltInput !== getCurrentInputText()) {
    plan = await buildArrangement({ silent: true });
    if (!plan) return;
  }

  stopArrangement({ silent: true });
  musicLabState.isPlaying = true;
  syncArrangementButtons();
  await _startArrangementPlayback(plan);
}

function stopArrangement(options = {}) {
  musicLabState.playTimers.forEach(timer => window.clearTimeout(timer));
  musicLabState.playTimers = [];
  document.querySelectorAll('.timeline-slot.is-playing').forEach(node => node.classList.remove('is-playing'));
  if (musicLabState.isPlaying) {
    panicAudio();
  }
  musicLabState.isPlaying = false;
  syncArrangementButtons();
  if (!options.silent) {
    setTransportStatus('Transport stopped.', 'ready');
  }
}

function toggleLoop() {
  musicLabState.loopEnabled = !musicLabState.loopEnabled;
  const btn = document.getElementById('loopToggleBtn');
  if (btn) {
    btn.classList.toggle('active', musicLabState.loopEnabled);
    btn.setAttribute('aria-pressed', musicLabState.loopEnabled ? 'true' : 'false');
  }
}

async function exportMidi() {
  const input = getCurrentInputText();
  if (!input) return;
  const exportBtn = document.getElementById('arrangementExportBtn');
  if (exportBtn) exportBtn.disabled = true;
  setTransportStatus('Exporting MIDI\u2026', 'busy');
  try {
    const tempoEl = document.getElementById('labTempo');
    const meterEl = document.getElementById('labMeter');
    const countInEl = document.getElementById('labCountIn');
    const bassEl = document.getElementById('labBassEnabled');
    const payload = {
      input,
      tempo: tempoEl ? parseInt(tempoEl.value) : 96,
      meter: meterEl ? parseInt(meterEl.value) : 4,
      count_in_beats: countInEl ? parseInt(countInEl.value) : 4,
      groove: musicLabState.selectedGroove || 'anthem',
      bass_enabled: bassEl ? bassEl.checked : true,
    };
    const response = await fetch('/arrangement/export-midi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || 'Export failed');
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'arrangement.mid';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setTransportStatus('MIDI exported.', 'ready');
  } catch (err) {
    setTransportStatus('Export failed: ' + err.message, 'warn');
  } finally {
    syncArrangementButtons();
  }
}

function setToneLibraryStatus(message) {
  const status = document.getElementById('toneLibraryStatus');
  if (!status) return;
  status.textContent = message || '';
}

function openToneModelPicker() {
  const input = document.getElementById('toneModelInput');
  if (!input) return;
  input.value = '';
  input.click();
}

function openToneIrPicker(toneId = null) {
  toneLibraryState.pendingToneForIr = toneId;
  const input = document.getElementById('toneIrInput');
  if (!input) return;
  input.value = '';
  input.click();
}

function renderToneLibrary() {
  const container = document.getElementById('toneLibraryList');
  if (!container) return;
  container.innerHTML = '';

  if (!toneLibraryState.tones.length) {
    container.innerHTML = `
      <div class="arrangement-placeholder">
        <strong>No tones imported yet.</strong>
        <span>Bring in a \`.nam\` model to start building your local tone slot list.</span>
      </div>
    `;
    return;
  }

  toneLibraryState.tones.forEach(tone => {
    const row = document.createElement('div');
    row.className = 'tone-row';

    const top = document.createElement('div');
    top.className = 'tone-row-top';
    const name = document.createElement('div');
    name.className = 'tone-name';
    name.textContent = tone.name || tone.model_file;
    top.appendChild(name);

    const compat = document.createElement('span');
    const compatKey = String(tone.compatibility || 'unknown').toLowerCase();
    compat.className = `tone-pill compat-${compatKey}`;
    compat.textContent = compatKey;
    top.appendChild(compat);
    row.appendChild(top);

    const meta = document.createElement('div');
    meta.className = 'tone-meta';
    const arch = document.createElement('span');
    arch.className = 'tone-pill';
    arch.textContent = `arch: ${tone.metadata?.architecture || 'n/a'}`;
    const version = document.createElement('span');
    version.className = 'tone-pill';
    version.textContent = `v: ${tone.metadata?.version || 'n/a'}`;
    meta.appendChild(arch);
    meta.appendChild(version);
    row.appendChild(meta);

    const sub = document.createElement('div');
    sub.className = 'tone-sub';
    sub.textContent = tone.ir_file ? `IR: ${tone.ir_file}` : 'IR: none attached';
    row.appendChild(sub);

    const actions = document.createElement('div');
    actions.className = 'tone-actions';

    const irSelect = document.createElement('select');
    irSelect.className = 'tone-select';
    const noneOpt = document.createElement('option');
    noneOpt.value = '';
    noneOpt.textContent = 'No IR';
    irSelect.appendChild(noneOpt);
    (toneLibraryState.irs || []).forEach(ir => {
      const opt = document.createElement('option');
      opt.value = ir.id;
      opt.textContent = ir.name || ir.file;
      if (tone.ir_id && tone.ir_id === ir.id) {
        opt.selected = true;
      }
      irSelect.appendChild(opt);
    });
    irSelect.addEventListener('change', () => {
      attachIrToTone(tone.id, irSelect.value || null);
    });
    actions.appendChild(irSelect);

    const attachBtn = document.createElement('button');
    attachBtn.className = 'btn-transport ghost';
    attachBtn.type = 'button';
    attachBtn.textContent = 'Import IR for Tone';
    attachBtn.addEventListener('click', () => openToneIrPicker(tone.id));
    actions.appendChild(attachBtn);

    const removeBtn = document.createElement('button');
    removeBtn.className = 'btn-transport ghost';
    removeBtn.type = 'button';
    removeBtn.textContent = 'Remove';
    removeBtn.addEventListener('click', () => removeTone(tone.id));
    actions.appendChild(removeBtn);

    row.appendChild(actions);
    container.appendChild(row);
  });
}

async function refreshToneLibrary() {
  try {
    const response = await appFetch('/tone/library');
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || 'Tone library request failed');
    }
    const library = body.library || { tones: [], irs: [] };
    toneLibraryState.tones = library.tones || [];
    toneLibraryState.irs = library.irs || [];
    renderToneLibrary();
    setToneLibraryStatus(`Loaded ${toneLibraryState.tones.length} tone(s).`);
  } catch (err) {
    setToneLibraryStatus(`Tone library unavailable: ${err.message}`);
  }
}

async function importToneModel(file) {
  const formData = new FormData();
  formData.append('file', file, file.name);
  try {
    const response = await appFetch('/tone/import-model', { method: 'POST', body: formData });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || 'Model import failed');
    }
    toneLibraryState.tones = body.library?.tones || [];
    toneLibraryState.irs = body.library?.irs || [];
    renderToneLibrary();
    setToneLibraryStatus(`Imported model: ${body.tone?.name || file.name}`);
  } catch (err) {
    setToneLibraryStatus(`Model import failed: ${err.message}`);
  }
}

async function importToneIr(file, toneId = null) {
  const formData = new FormData();
  formData.append('file', file, file.name);
  if (toneId) formData.append('tone_id', toneId);
  try {
    const response = await appFetch('/tone/import-ir', { method: 'POST', body: formData });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || 'IR import failed');
    }
    toneLibraryState.tones = body.library?.tones || [];
    toneLibraryState.irs = body.library?.irs || [];
    renderToneLibrary();
    setToneLibraryStatus(`Imported IR: ${body.ir?.name || file.name}`);
  } catch (err) {
    setToneLibraryStatus(`IR import failed: ${err.message}`);
  } finally {
    toneLibraryState.pendingToneForIr = null;
  }
}

async function attachIrToTone(toneId, irId) {
  try {
    const response = await appFetch('/tone/attach-ir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tone_id: toneId, ir_id: irId })
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || 'Attach failed');
    }
    toneLibraryState.tones = body.library?.tones || [];
    toneLibraryState.irs = body.library?.irs || [];
    renderToneLibrary();
  } catch (err) {
    setToneLibraryStatus(`IR attach failed: ${err.message}`);
  }
}

async function removeTone(toneId) {
  try {
    const response = await appFetch('/tone/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tone_id: toneId })
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || 'Tone remove failed');
    }
    toneLibraryState.tones = body.library?.tones || [];
    toneLibraryState.irs = body.library?.irs || [];
    renderToneLibrary();
    setToneLibraryStatus('Tone removed.');
  } catch (err) {
    setToneLibraryStatus(`Tone remove failed: ${err.message}`);
  }
}

function initToneLibrary() {
  const modelInput = document.getElementById('toneModelInput');
  if (modelInput) {
    modelInput.addEventListener('change', event => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      importToneModel(file);
    });
  }
  const irInput = document.getElementById('toneIrInput');
  if (irInput) {
    irInput.addEventListener('change', event => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      importToneIr(file, toneLibraryState.pendingToneForIr);
    });
  }
  refreshToneLibrary();
}

function initMusicLab() {
  renderGrooveOptions();
  syncMusicLabSummary();
  clearArrangementTimeline(
    'Build the first loop.',
    'The planner will resolve a key, split the progression into bars, and expose each chord slot as a playable timeline cell.'
  );
  syncArrangementButtons();
}

function doConvert() {
  const input = getCurrentInputText();
  if (!input) return;

  const btn = document.getElementById('convertBtn');
  btn.classList.add('loading');

  appFetch('/convert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input })
  })
  .then(r => r.json())
  .then(data => {
    btn.classList.remove('loading');
    renderOutput(data);
    if (!data.error) {
      buildArrangement({ silent: true });
    } else {
      musicLabState.plan = null;
      musicLabState.lastBuiltInput = '';
      musicLabState.activeSlotKey = '';
      syncMusicLabSummary();
      clearArrangementTimeline('Convert the chart first.', 'The arrangement planner uses the current progression text and key context.');
    }
  })
  .catch(err => {
    btn.classList.remove('loading');
    renderOutput({ error: String(err) });
    musicLabState.plan = null;
    musicLabState.lastBuiltInput = '';
    musicLabState.activeSlotKey = '';
    syncMusicLabSummary();
    clearArrangementTimeline('Conversion failed.', String(err));
  });
}

function renderOutput(data) {
  const box = document.getElementById('outputBox');
  const fbSection = document.getElementById('fbSection');

  if (data.error) {
    box.className = 'output-box has-error animate-in';
    box.innerHTML = `<span class="output-error">⚠ ${escapeHtml(data.error)}</span>`;
    fbSection.classList.remove('active');
    if (document.getElementById('panelText').style.display !== 'none') {
      const inputArea = document.getElementById('inputArea');
      if (inputArea) inputArea.focus();
    }
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
    html += `<span class="output-key interactive-token" role="button" tabindex="0" onclick="handleTokenInteraction(this, {type:'key', keyTonic:'${keyTonic}', keyMode:'${keyMode}'})" onkeydown="handleTokenKeydown(event, this, {type:'key', keyTonic:'${keyTonic}', keyMode:'${keyMode}'})">${escapeHtml(keyLine)}</span>\n`;

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

          html += `<span class="output-progression interactive-token" role="button" tabindex="0" onclick="handleTokenInteraction(this, ${dataJson})" onkeydown="handleTokenKeydown(event, this, ${dataJson})">${escapeHtml(token)}</span>`;
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
  stopArrangement({ silent: true });
  builderClear();
  resetStage();
  const inputArea = document.getElementById('inputArea');
  if (inputArea) {
    inputArea.value = '';
    // Focus if Text tab is active
    if (document.getElementById('panelText').style.display !== 'none') {
      inputArea.focus();
    }
  }
  const box = document.getElementById('outputBox');
  box.className = 'output-box';
  box.innerHTML = '<span class="output-placeholder">Result will appear here&hellip;</span>';
  document.getElementById('fbSection').classList.remove('active');
  selectedChord = null;
  currentKey = { tonic: 'C', mode: 'Major' };
  musicLabState.plan = null;
  musicLabState.lastBuiltInput = '';
  musicLabState.activeSlotKey = '';
  syncMusicLabSummary();
  clearArrangementTimeline(
    'Build the first loop.',
    'The planner will resolve a key, split the progression into bars, and expose each chord slot as a playable timeline cell.'
  );
  panicAudio();
}

// ── Builder Logic ───────────────────────────────────────────────────────────

let builderMode = 'nns';  // 'chords' | 'nns'
let builderTokens = [];      // { type: 'chord'|'sep', text: string }
let stagedNote = '';         // e.g. "C" or "b3"
let stagedQuality = '';      // e.g. "m7" or ""
let nnsAccidental = '';      // '' | 'b' | '#'
let scaleLockEnabled = true; // auto-assign diatonic quality on degree click

const BUILDER_NOTES = ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'];

const CHORD_QUALITIES = [
  { label: 'maj',   suffix: '' },
  { label: 'm',     suffix: 'm' },
  { label: '7',     suffix: '7' },
  { label: 'm7',    suffix: 'm7' },
  { label: 'maj7',  suffix: 'maj7' },
  { label: 'mMaj7', suffix: 'mMaj7' },
  { label: 'm7b5',  suffix: 'm7b5' },
  { label: 'dim',   suffix: 'dim' },
  { label: 'dim7',  suffix: 'dim7' },
  { label: 'aug',   suffix: 'aug' },
  { label: 'sus2',  suffix: 'sus2' },
  { label: 'sus4',  suffix: 'sus4' },
  { label: 'add9',  suffix: 'add9' },
];

const NNS_QUALITIES = [
  { label: 'maj',  suffix: '' },
  { label: 'm',    suffix: 'm' },
  { label: '7',    suffix: '(7)' },
  { label: 'm7',   suffix: 'm7' },
  { label: 'maj7', suffix: 'maj7' },
  { label: 'dim',  suffix: 'dim' },
  { label: 'aug',  suffix: 'aug' },
  { label: 'sus4', suffix: 'sus4' },
];

// Diatonic chord qualities per scale degree (index 0 = degree 1 … index 6 = degree 7).
// Suffixes match NNS_QUALITIES.suffix values.
const DIATONIC_QUALITIES = {
  'Major':          ['', 'm', 'm', '', '', 'm', 'dim'],
  'Minor':          ['m', 'dim', '', 'm', 'm', '', ''],
  'Dorian':         ['m', 'm', '', '', 'm', 'dim', ''],
  'Mixolydian':     ['', 'm', 'dim', '', 'm', 'm', ''],
  'Phrygian':       ['m', '', '', 'm', 'dim', '', 'm'],
  'Lydian':         ['', '', 'm', 'dim', '', 'm', 'm'],
  'Harmonic Minor': ['m', 'dim', 'aug', 'm', '', '', 'dim'],
};

// The actual NNS degree TOKEN emitted per scale position (may include b/# prefix).
// Fixes edge case: modal/minor scales use altered degrees (b3, b6, b7, b2, #4)
// that must be explicit in NNS notation, not just the bare digit.
const DIATONIC_NNS_DEGREES = {
  'Major':          ['1',  '2',  '3',  '4',  '5',  '6',  '7'],
  'Minor':          ['1',  '2',  'b3', '4',  '5',  'b6', 'b7'],
  'Dorian':         ['1',  '2',  'b3', '4',  '5',  '6',  'b7'],
  'Mixolydian':     ['1',  '2',  '3',  '4',  '5',  '6',  'b7'],
  'Phrygian':       ['1',  'b2', 'b3', '4',  '5',  'b6', 'b7'],
  'Lydian':         ['1',  '2',  '3',  '#4', '5',  '6',  '7'],
  'Harmonic Minor': ['1',  '2',  'b3', '4',  '5',  'b6', '7'],
};

// Scale tooltip info: alias, W/H step pattern, degree formula, chord qualities.
const SCALE_INFO = {
  'Major':          { alias: 'Ionian',         pattern: 'W W H W W W H', degrees: '1  2  3  4  5  6  7',  chords: 'I  ii  iii IV  V  vi  vii°' },
  'Minor':          { alias: 'Aeolian',        pattern: 'W H W W H W W', degrees: '1  2  ♭3 4  5  ♭6 ♭7', chords: 'i  ii° III iv  v  VI  VII' },
  'Dorian':         { alias: 'Dorian mode',    pattern: 'W H W W W H W', degrees: '1  2  ♭3 4  5  6  ♭7', chords: 'i  ii  III IV  v  vi° VII' },
  'Mixolydian':     { alias: 'Mixolydian',     pattern: 'W W H W W H W', degrees: '1  2  3  4  5  6  ♭7', chords: 'I  ii  iii°IV  v  vi  VII' },
  'Phrygian':       { alias: 'Phrygian mode',  pattern: 'H W W W H W W', degrees: '1  ♭2 ♭3 4  5  ♭6 ♭7', chords: 'i  II  III iv  v° VI  vii' },
  'Lydian':         { alias: 'Lydian mode',    pattern: 'W W W H W W H', degrees: '1  2  3  ♯4 5  6  7',  chords: 'I  II  iii ♯iv°V  vi  vii' },
  'Harmonic Minor': { alias: 'Harm. Minor',    pattern: 'W H W W H A H', degrees: '1  2  ♭3 4  5  ♭6 7',  chords: 'i  ii° ♭III iv  V  VI  vii°' },
};

const DIATONIC_HINT_LABELS = {
  '': 'maj', 'm': 'min', 'dim': 'dim', 'aug': 'aug',
  '(7)': 'dom7', 'm7': 'min7', 'maj7': 'maj7',
};

// Map extended scale names to the major/minor keyword the backend understands.
const SCALE_TO_QUALITY_OUTPUT = {
  'Major': 'major', 'Lydian': 'major', 'Mixolydian': 'major',
  'Minor': 'minor', 'Dorian': 'minor', 'Phrygian': 'minor', 'Harmonic Minor': 'minor',
};

function initBuilder() {
  // Note palette
  const notePalette = document.getElementById('notePalette');
  BUILDER_NOTES.forEach(note => {
    const btn = document.createElement('button');
    btn.type = 'button';
    const isAcc = note.includes('#') || note.includes('b');
    btn.className = 'note-btn' + (isAcc ? ' accidental' : '');
    btn.dataset.note = note;
    btn.textContent = note;
    btn.addEventListener('click', () => selectNote(note, btn));
    notePalette.appendChild(btn);
  });

  buildQualityPalette('qualityPalette', CHORD_QUALITIES, (suffix, btn) => {
    document.querySelectorAll('#qualityPalette .quality-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-pressed', 'false');
    });
    btn.classList.add('active');
    btn.setAttribute('aria-pressed', 'true');
    stagedQuality = suffix;
    updateStageDisplay();
  });

  // Number palette with accidental selector
  const numberPalette = document.getElementById('numberPalette');

  const accCol = document.createElement('div');
  accCol.className = 'acc-col';
  const accColLabel = document.createElement('div');
  accColLabel.className = 'acc-col-label';
  accColLabel.textContent = 'Acc';
  accCol.appendChild(accColLabel);

  [['b', 'b'], ['', '\u266e'], ['#', '#']].forEach(([acc, label]) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'acc-btn' + (acc === '' ? ' selected' : '');
    btn.dataset.acc = acc;
    btn.textContent = label;
    btn.title = acc === '' ? 'Natural' : acc === 'b' ? 'Flat' : 'Sharp';
    btn.setAttribute('aria-pressed', acc === '' ? 'true' : 'false');
    btn.addEventListener('click', () => {
      document.querySelectorAll('.acc-btn').forEach(b => {
        b.classList.remove('selected');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('selected');
      btn.setAttribute('aria-pressed', 'true');
      nnsAccidental = acc;
      if (stagedNote) {
        const num = stagedNote.replace(/^[b#]/, '');
        stagedNote = nnsAccidental + num;
        updateStageDisplay();
      }
    });
    accCol.appendChild(btn);
  });
  numberPalette.appendChild(accCol);

  for (let n = 1; n <= 7; n++) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'num-btn';
    btn.dataset.num = n;

    const digitSpan = document.createElement('span');
    digitSpan.className = 'num-btn-digit';
    digitSpan.textContent = n;

    const hintSpan = document.createElement('span');
    hintSpan.className = 'num-btn-hint';
    hintSpan.dataset.forDegree = n;

    btn.appendChild(digitSpan);
    btn.appendChild(hintSpan);

    btn.addEventListener('click', () => {
      if (scaleLockEnabled) {
        const scaleName = document.getElementById('keyQuality').value;
        const degrees  = DIATONIC_NNS_DEGREES[scaleName] || DIATONIC_NNS_DEGREES['Major'];
        const qualities = DIATONIC_QUALITIES[scaleName]  || DIATONIC_QUALITIES['Major'];
        stagedNote = degrees[n - 1];   // e.g. "b3", "#4", or plain "1"
        const q = qualities[n - 1];
        stagedQuality = q;
        // Sync quality palette
        document.querySelectorAll('#nnsQualityPalette .quality-btn').forEach(b => {
          const isMatch = b.dataset.suffix === q;
          b.classList.toggle('active', isMatch);
          b.setAttribute('aria-pressed', isMatch ? 'true' : 'false');
        });
        // Sync accidental column to reflect the degree we locked in
        const lockedAcc = stagedNote.startsWith('b') ? 'b' : stagedNote.startsWith('#') ? '#' : '';
        nnsAccidental = lockedAcc;
        document.querySelectorAll('.acc-btn').forEach(b => {
          const match = b.dataset.acc === lockedAcc;
          b.classList.toggle('selected', match);
          b.setAttribute('aria-pressed', match ? 'true' : 'false');
        });
      } else {
        stagedNote = nnsAccidental + n;
      }
      commitStaged();
    });
    numberPalette.appendChild(btn);
  }

  buildQualityPalette('nnsQualityPalette', NNS_QUALITIES, (suffix, btn) => {
    document.querySelectorAll('#nnsQualityPalette .quality-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-pressed', 'false');
    });
    btn.classList.add('active');
    btn.setAttribute('aria-pressed', 'true');
    stagedQuality = suffix;
    updateStageDisplay();
  });

  updateDiatonicHints();
  updateScaleTooltip();
}

function buildQualityPalette(id, qualities, handler) {
  const palette = document.getElementById(id);
  qualities.forEach((q, i) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'quality-btn' + (i === 0 ? ' active' : '');
    btn.dataset.suffix = q.suffix;
    btn.textContent = q.label;
    btn.setAttribute('aria-pressed', i === 0 ? 'true' : 'false');
    btn.addEventListener('click', () => handler(q.suffix, btn));
    palette.appendChild(btn);
  });
}

function toggleScaleLock() {
  scaleLockEnabled = !scaleLockEnabled;
  const btn = document.getElementById('scaleLockBtn');
  btn.classList.toggle('active', scaleLockEnabled);
  btn.setAttribute('aria-pressed', scaleLockEnabled ? 'true' : 'false');
  updateDiatonicHints();
}

function onKeyQualityChange() {
  updateDiatonicHints();
  updateScaleTooltip();
}

function updateDiatonicHints() {
  const scaleName = document.getElementById('keyQuality').value;
  const qualities = DIATONIC_QUALITIES[scaleName] || DIATONIC_QUALITIES['Major'];
  const degrees   = DIATONIC_NNS_DEGREES[scaleName] || DIATONIC_NNS_DEGREES['Major'];
  document.querySelectorAll('.num-btn-hint').forEach(span => {
    const pos = parseInt(span.dataset.forDegree);
    if (scaleLockEnabled && pos >= 1 && pos <= 7) {
      const q   = qualities[pos - 1];
      const deg = degrees[pos - 1];  // e.g. "b3", "#4", "1"
      // Show ♭/♯ prefix when the scale step is an altered degree
      const acc = deg.startsWith('b') ? '\u266d' : deg.startsWith('#') ? '\u266f' : '';
      const ql  = DIATONIC_HINT_LABELS[q] !== undefined ? DIATONIC_HINT_LABELS[q] : 'maj';
      span.textContent = acc + ql;
    } else {
      span.textContent = '';
    }
  });
}

function updateScaleTooltip() {
  const scaleName = document.getElementById('keyQuality').value;
  const info = SCALE_INFO[scaleName];
  const pop = document.getElementById('scaleTipPopup');
  if (!pop || !info) return;
  pop.innerHTML =
    '<span class="stt-name">' + scaleName + ' <em>(' + info.alias + ')</em></span>' +
    '<span class="stt-row"><b>Steps&nbsp;</b>' + info.pattern + '</span>' +
    '<span class="stt-row"><b>Degrees</b> ' + info.degrees + '</span>' +
    '<span class="stt-row"><b>Chords&nbsp;</b>' + info.chords + '</span>';
}

function switchInputTab(tab) {
  const isBuilder = tab === 'builder';
  document.getElementById('panelBuilder').style.display = isBuilder ? '' : 'none';
  document.getElementById('panelText').style.display = isBuilder ? 'none' : '';
  document.getElementById('tabBuilder').classList.toggle('active', isBuilder);
  document.getElementById('tabBuilder').setAttribute('aria-selected', isBuilder);
  document.getElementById('tabText').classList.toggle('active', !isBuilder);
  document.getElementById('tabText').setAttribute('aria-selected', !isBuilder);
  if (!isBuilder) document.getElementById('inputArea').focus();
}

function setBuilderMode(mode) {
  builderMode = mode;
  const isChords = mode === 'chords';
  document.getElementById('modeChordsBtn').classList.toggle('active', isChords);
  document.getElementById('modeChordsBtn').setAttribute('aria-pressed', isChords);
  document.getElementById('modeNnsBtn').classList.toggle('active', !isChords);
  document.getElementById('modeNnsBtn').setAttribute('aria-pressed', !isChords);
  document.getElementById('chordBuilder').style.display = isChords ? '' : 'none';
  document.getElementById('nnsBuilder').style.display = isChords ? 'none' : '';
  document.getElementById('keyRow').classList.toggle('disabled', isChords);
  resetStage();
}

function selectNote(note, btn) {
  stagedNote = note;
  document.querySelectorAll('.note-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  updateStageDisplay();
  // Auto-commit with current quality
  commitStaged();
}

function updateStageDisplay() {
  const track = document.getElementById('progressionTrack');
  if (!track) return;
  // Remove any existing staged preview
  const existing = track.querySelector('.prog-chip.staged');
  if (existing) existing.remove();
  if (!stagedNote) return;
  // Show staged preview chip
  const preview = document.createElement('span');
  preview.className = 'prog-chip staged';
  preview.textContent = stagedNote + (stagedQuality || '') + ' \u2026';
  track.appendChild(preview);
}

function commitStaged() {
  if (!stagedNote) return;
  const chord = stagedNote + stagedQuality;
  builderTokens.push({ type: 'chord', text: chord });
  renderProgressionTrack();
  resetStage();
}

function builderUndo() {
  if (builderTokens.length === 0) return;
  builderTokens.pop();
  normalizeBuilderTokens();
  renderProgressionTrack();
}

function builderClear() {
  builderTokens = [];
  renderProgressionTrack();
}

function normalizeBuilderTokens() {
  if (builderTokens.length === 0) return;

  const normalized = [];
  builderTokens.forEach(token => {
    if (!token || (token.type !== 'chord' && token.type !== 'sep')) return;

    const text = typeof token.text === 'string' ? token.text : '';
    if (!text) return;

    if (token.type === 'sep' && (normalized.length === 0 || normalized[normalized.length - 1].type === 'sep')) {
      return;
    }

    normalized.push({ type: token.type, text });
  });

  if (normalized.length > 0 && normalized[normalized.length - 1].type === 'sep') {
    normalized.pop();
  }

  builderTokens = normalized;
}

function ensureProgressionEmptyNode() {
  let empty = document.getElementById('progEmpty');
  if (empty) return empty;

  empty = document.createElement('span');
  empty.className = 'progression-empty';
  empty.id = 'progEmpty';
  empty.textContent = 'Pick a note below to start\u2026';
  return empty;
}

function resetStage() {
  stagedNote = '';
  stagedQuality = '';
  document.querySelectorAll('.note-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.num-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('#qualityPalette .quality-btn').forEach((b, i) => {
    b.classList.toggle('active', i === 0);
    b.setAttribute('aria-pressed', i === 0);
  });
  document.querySelectorAll('#nnsQualityPalette .quality-btn').forEach((b, i) => {
    b.classList.toggle('active', i === 0);
    b.setAttribute('aria-pressed', i === 0);
  });
  updateStageDisplay();
}

function renderProgressionTrack() {
  normalizeBuilderTokens();

  const track = document.getElementById('progressionTrack');
  const empty = ensureProgressionEmptyNode();

  track.innerHTML = '';

  if (builderTokens.length === 0) {
    track.classList.remove('has-items');
    empty.style.display = '';
    track.appendChild(empty);
    return;
  }

  track.classList.add('has-items');
  if (empty) empty.style.display = 'none';

  builderTokens.forEach((token, idx) => {
    const chip = document.createElement('span');
    chip.className = 'prog-chip' + (token.type === 'sep' ? ' separator' : '');

    const label = document.createElement('span');
    label.textContent = token.text.trim() || token.text;
    chip.appendChild(label);

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'prog-chip-del';
    del.textContent = '\u00d7';
    del.title = 'Remove';
    del.setAttribute('aria-label', 'Remove ' + token.text.trim());
    del.addEventListener('click', () => {
      builderTokens.splice(idx, 1);
      normalizeBuilderTokens();
      renderProgressionTrack();
    });
    chip.appendChild(del);

    track.appendChild(chip);
  });
}

function buildProgressionString() {
  if (builderTokens.length === 0) return '';

  let str = '';
  for (let i = 0; i < builderTokens.length; i++) {
    const tok = builderTokens[i];
    const prev = i > 0 ? builderTokens[i - 1] : null;
    if (tok.type === 'chord' && prev && prev.type === 'chord') {
      str += ' ' + tok.text;
    } else {
      str += tok.text;
    }
  }

  if (builderMode === 'nns') {
    const keyNote = document.getElementById('keyNote').value;
    const keyQuality = document.getElementById('keyQuality').value;
    const qualityOut = SCALE_TO_QUALITY_OUTPUT[keyQuality] || keyQuality.toLowerCase();
    str += ' in ' + keyNote + ' ' + qualityOut;
  }

  return str.trim();
}

// ── Fretboard Logic ────────────────────────────────────────────────────────

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const SCALE_DEGREES = {
  "Major":          [0, 2, 4, 5, 7, 9, 11],  // Ionian
  "Minor":          [0, 2, 3, 5, 7, 8, 10],  // Aeolian
  "Dorian":         [0, 2, 3, 5, 7, 9, 10],
  "Mixolydian":     [0, 2, 4, 5, 7, 9, 10],
  "Phrygian":       [0, 1, 3, 5, 7, 8, 10],
  "Lydian":         [0, 2, 4, 6, 7, 9, 11],
  "Harmonic Minor": [0, 2, 3, 5, 7, 8, 11],
};

const TUNINGS = {
  guitar: [4, 11, 7, 2, 9, 4], // E B G D A E
  bass: [7, 2, 9, 4],       // G D A E
  bass5: [7, 2, 9, 4, 11]    // G D A E B
};

const MIDI_TUNINGS = {
  guitar: [64, 59, 55, 50, 45, 40], // E4 B3 G3 D3 A2 E2
  bass: [43, 38, 33, 28],           // G2 D2 A1 E1
  bass5: [43, 38, 33, 28, 23]       // G2 D2 A1 E1 B0
};

let currentKey = { tonic: "C", mode: "Major" };
let selectedChord = null;
let visibleDegrees = new Set([1, 2, 3, 4, 5, 6, 7]);
let resizeTimer = null;
const activeFretPointers = new Map();

function getNoteValue(name) {
  const map = {
    "C":0,"B#":0,"C#":1,"Db":1,"D":2,"D#":3,"Eb":3,"E":4,"Fb":4,"F":5,"E#":5,
    "F#":6,"Gb":6,"G":7,"G#":8,"Ab":8,"A":9,"A#":10,"Bb":10,"B":11,"Cb":11
  };
  return map[name.replace(/maj7|mmaj7|min|maj|dim|aug|sus2|sus4|m|7|6|9|11|13|add\d+|[#b]\d+/gi, "")] ?? 0;
}

function getStringSpacing() {
  if (window.matchMedia('(min-width: 1700px)').matches) return 30;
  if (window.matchMedia('(min-width: 1280px)').matches) return 28;
  if (window.matchMedia('(min-width: 900px)').matches) return 26;
  return 22;
}

function updateFretboard() {
  const container = document.getElementById('fretboard');
  const instrument = document.getElementById('instrumentSelect').value;
  const viewMode = document.getElementById('viewModeSelect').value;
  const tuning = TUNINGS[instrument];
  const midiTuning = MIDI_TUNINGS[instrument] || [];
  const numFrets = 15;
  const stringSpacing = getStringSpacing();

  container.innerHTML = '';
  container.style.height = (tuning.length * stringSpacing) + 'px';

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
      const midiVal = (midiTuning[stringIdx] ?? 48) + fret;
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
        isTonic = selectedChord.root != null ? noteVal === getNoteValue(selectedChord.root) : false;
      }

      if (shouldShow) {
        const dot = document.createElement('div');
        const isSelectedTonic = isTonic || (viewMode === 'chord' && selectedChord && selectedChord.type === 'nns' && degreeInfo.degree === parseInt(selectedChord.text.match(/[1-7]/)[0]));
        dot.className = `fb-note-dot playable degree-${degreeInfo.degree} ${isSelectedTonic ? 'tonic' : ''}`;
        dot.style.left = ((fret === 0 ? 0.5 : fret - 0.5) * (100 / numFrets)) + '%';
        dot.style.top = ((stringIdx + 0.5) * (100 / tuning.length)) + '%';
        dot.textContent = label;
        dot.dataset.midi = String(midiVal);
        wireFretDotAudio(dot, midiVal);
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
  const rootVal = getChordRootValue(chord, key);

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

function getChordRootValue(chord, key) {
  if (chord.type === 'nns') {
    const steps = {"1":0,"b2":1,"2":2,"b3":3,"3":4,"4":5,"#4":6,"5":7,"b6":8,"6":9,"b7":10,"7":11};
    const degMatch = chord.text.match(/^[#b]?[1-7]/);
    const degree = degMatch ? degMatch[0] : "1";
    return (getNoteValue(key.tonic) + (steps[degree] || 0)) % 12;
  }
  return getNoteValue(chord.root || chord.text);
}

function getChordMidiNotes(chord, key) {
  const rootVal = getChordRootValue(chord, key);
  const pcs = getChordNotes(chord, key);
  const baseRoot = 48 + rootVal;
  const midis = [];
  let previous = baseRoot - 1;

  pcs.forEach(pc => {
    let midi = baseRoot + ((pc - rootVal + 12) % 12);
    while (midi <= previous) midi += 12;
    if (midis.indexOf(midi) === -1) {
      midis.push(midi);
      previous = midi;
    }
  });

  return midis.slice(0, 8);
}

function wireFretDotAudio(dot, midiVal) {
  dot.setAttribute('tabindex', '0');
  dot.setAttribute('role', 'button');
  dot.setAttribute('aria-label', 'Play note ' + midiVal);

  const release = (pointerId) => {
    if (!activeFretPointers.has(pointerId)) return;
    const midi = activeFretPointers.get(pointerId);
    activeFretPointers.delete(pointerId);
    noteOffPreview(midi, 0);
  };

  dot.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    activeFretPointers.set(event.pointerId, midiVal);
    if (dot.setPointerCapture) dot.setPointerCapture(event.pointerId);
    noteOnPreview(midiVal, 96, 0);
  });

  dot.addEventListener('pointerup', (event) => release(event.pointerId));
  dot.addEventListener('pointercancel', (event) => release(event.pointerId));
  dot.addEventListener('pointerleave', (event) => release(event.pointerId));
  dot.addEventListener('lostpointercapture', (event) => release(event.pointerId));

  dot.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      playNotePreview(midiVal, 96, 450, 0);
    }
  });
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
    const isActive = visibleDegrees.has(d);
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
}

function focusMusicalObject(data) {
  currentKey = { tonic: data.keyTonic, mode: data.keyMode };
  if (data.type === 'chord' || data.type === 'nns') {
    selectedChord = data;
    document.getElementById('viewModeSelect').value = 'chord';
    document.getElementById('fbSection').classList.add('active');
  } else {
    selectedChord = null;
    document.getElementById('viewModeSelect').value = 'scale';
  }
  updateFretboard();
}

function highlightToken(tokenEl, data) {
  document.querySelectorAll('.interactive-token').forEach(el => el.classList.remove('active-highlight'));
  tokenEl.classList.add('active-highlight');
  focusMusicalObject(data);
}

function handleTokenInteraction(tokenEl, data) {
  highlightToken(tokenEl, data);
  if (data.type !== 'chord' && data.type !== 'nns') return;
  const midis = getChordMidiNotes(data, currentKey);
  if (midis.length > 0) playChordPreview(midis, 'strum', 28, 700, 96, 0);
}

function handleTokenKeydown(event, tokenEl, data) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    handleTokenInteraction(tokenEl, data);
  }
}

// Keyboard shortcut
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    doConvert();
  }
});

window.addEventListener('resize', () => {
  if (!document.getElementById('fbSection').classList.contains('active')) return;
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(updateFretboard, 120);
});

// Init
window.addEventListener('load', () => {
  initBuilder();
  initMusicLab();
  initToneLibrary();
  refreshAudioStatus();
});

window.addEventListener('beforeunload', () => {
  stopArrangement({ silent: true });
  panicAudio();
});
</script>
</body>
</html>
"""


_DEFAULT_APP = GuiApp()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    _DEFAULT_APP.run()


if __name__ == "__main__":
    main()
