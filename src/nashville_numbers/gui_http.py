"""HTTP request handling for the embedded GUI."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from .audio import AudioInstallError, AudioUnavailableError


def build_handler(
    *,
    get_html: Callable[[], str],
    get_audio_service: Callable[[], Any],
    convert_text: Callable[[str], str],
    get_max_input_length: Callable[[], int],
    runtime_install_job: dict[str, Any],
    runtime_install_lock: threading.Lock,
    run_runtime_install: Callable[[], None],
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        """Minimal request handler serving the single-page app and a JSON API."""

        def log_message(self, format: str, *args: object) -> None:  # silence access logs
            pass

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                self._send_html(get_html())
            elif parsed.path == "/audio/status":
                self._send_json(get_audio_service().status())
            elif parsed.path == "/audio/install-runtime/status":
                with runtime_install_lock:
                    self._send_json(dict(runtime_install_job))
            else:
                self._send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/convert":
                self._handle_convert()
                return
            if parsed.path == "/audio/install-default":
                self._handle_audio_install_default()
                return
            if parsed.path == "/audio/play-note":
                self._handle_audio_play_note()
                return
            if parsed.path == "/audio/note-on":
                self._handle_audio_note_on()
                return
            if parsed.path == "/audio/note-off":
                self._handle_audio_note_off()
                return
            if parsed.path == "/audio/play-chord":
                self._handle_audio_play_chord()
                return
            if parsed.path == "/audio/panic":
                self._handle_audio_panic()
                return
            if parsed.path == "/audio/install-runtime":
                self._handle_audio_install_runtime()
                return
            self._send_json({"error": "not found"}, status=404)

        def _send_html(self, html: str) -> None:
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, obj: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_payload(self) -> dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json({"error": "Invalid Content-Length header"}, status=400)
                return None
            if length > get_max_input_length():
                self._send_json({"error": "Payload too large"}, status=413)
                return None
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON in request body"}, status=400)
                return None
            if not isinstance(payload, dict):
                self._send_json({"error": "Expected JSON object"}, status=400)
                return None
            return payload

        def _int_field(
            self,
            payload: dict[str, Any],
            key: str,
            *,
            minimum: int,
            maximum: int,
            default: int | None = None,
            required: bool = False,
        ) -> int:
            value = payload.get(key, default)
            if value is None and required:
                raise ValueError(f"'{key}' is required")
            if value is None:
                raise ValueError(f"'{key}' is required")
            try:
                parsed = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"'{key}' must be an integer") from exc
            if parsed < minimum or parsed > maximum:
                raise ValueError(f"'{key}' must be between {minimum} and {maximum}")
            return parsed

        def _handle_convert(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            try:
                input_text = str(payload.get("input", "")).strip()
                if not input_text:
                    self._send_json({"error": "Empty input"})
                    return
                result = convert_text(input_text)
                self._send_json({"result": result})
            except (ValueError, KeyError, TypeError) as exc:
                self._send_json({"error": str(exc)})

        def _handle_audio_install_default(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            try:
                status = get_audio_service().install_default_pack()
                self._send_json({"status": status})
            except AudioUnavailableError as exc:
                self._send_json({"error": str(exc), "reason": exc.code}, status=409)
            except AudioInstallError as exc:
                self._send_json({"error": str(exc), "reason": exc.code}, status=500)
            except Exception as exc:
                self._send_json(
                    {"error": f"Failed to install pack: {exc}", "reason": "install_failed"},
                    status=500,
                )

        def _handle_audio_play_note(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            try:
                midi = self._int_field(payload, "midi", minimum=0, maximum=127, required=True)
                velocity = self._int_field(payload, "velocity", minimum=1, maximum=127, default=96)
                duration_ms = self._int_field(
                    payload, "duration_ms", minimum=20, maximum=5000, default=450
                )
                channel = self._int_field(payload, "channel", minimum=0, maximum=15, default=0)
                audio_service = get_audio_service()
                audio_service.play_note(
                    midi, velocity=velocity, duration_ms=duration_ms, channel=channel
                )
                self._send_json({"ok": True, "status": audio_service.status()})
            except ValueError as exc:
                self._send_json({"error": str(exc), "reason": "validation"}, status=400)
            except AudioUnavailableError as exc:
                self._send_json({"error": str(exc), "reason": exc.code}, status=409)
            except Exception as exc:
                self._send_json(
                    {"error": f"Audio playback failed: {exc}", "reason": "init_error"},
                    status=500,
                )

        def _handle_audio_note_on(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            try:
                midi = self._int_field(payload, "midi", minimum=0, maximum=127, required=True)
                velocity = self._int_field(payload, "velocity", minimum=1, maximum=127, default=96)
                channel = self._int_field(payload, "channel", minimum=0, maximum=15, default=0)
                audio_service = get_audio_service()
                audio_service.note_on(midi, velocity=velocity, channel=channel)
                self._send_json({"ok": True, "status": audio_service.status()})
            except ValueError as exc:
                self._send_json({"error": str(exc), "reason": "validation"}, status=400)
            except AudioUnavailableError as exc:
                self._send_json({"error": str(exc), "reason": exc.code}, status=409)
            except Exception as exc:
                self._send_json(
                    {"error": f"Audio note_on failed: {exc}", "reason": "init_error"},
                    status=500,
                )

        def _handle_audio_note_off(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            try:
                midi = self._int_field(payload, "midi", minimum=0, maximum=127, required=True)
                channel = self._int_field(payload, "channel", minimum=0, maximum=15, default=0)
                audio_service = get_audio_service()
                audio_service.note_off(midi, channel=channel)
                self._send_json({"ok": True, "status": audio_service.status()})
            except ValueError as exc:
                self._send_json({"error": str(exc), "reason": "validation"}, status=400)
            except AudioUnavailableError as exc:
                self._send_json({"error": str(exc), "reason": exc.code}, status=409)
            except Exception as exc:
                self._send_json(
                    {"error": f"Audio note_off failed: {exc}", "reason": "init_error"},
                    status=500,
                )

        def _handle_audio_play_chord(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            try:
                midis_value = payload.get("midis")
                if not isinstance(midis_value, list):
                    raise ValueError("'midis' must be an array of midi notes")
                if not (1 <= len(midis_value) <= 8):
                    raise ValueError("'midis' must contain between 1 and 8 notes")
                midis = [
                    self._int_field(
                        {"midi": value}, "midi", minimum=0, maximum=127, required=True
                    )
                    for value in midis_value
                ]
                style = str(payload.get("style", "strum")).strip().lower()
                if style not in {"block", "strum"}:
                    raise ValueError("'style' must be 'block' or 'strum'")
                strum_ms = self._int_field(payload, "strum_ms", minimum=5, maximum=120, default=28)
                note_ms = self._int_field(payload, "note_ms", minimum=50, maximum=5000, default=700)
                velocity = self._int_field(payload, "velocity", minimum=1, maximum=127, default=96)
                channel = self._int_field(payload, "channel", minimum=0, maximum=15, default=0)
                audio_service = get_audio_service()
                audio_service.play_chord(
                    midis,
                    style=style,
                    strum_ms=strum_ms,
                    note_ms=note_ms,
                    velocity=velocity,
                    channel=channel,
                )
                self._send_json({"ok": True, "status": audio_service.status()})
            except ValueError as exc:
                self._send_json({"error": str(exc), "reason": "validation"}, status=400)
            except AudioUnavailableError as exc:
                self._send_json({"error": str(exc), "reason": exc.code}, status=409)
            except Exception as exc:
                self._send_json(
                    {"error": f"Audio chord playback failed: {exc}", "reason": "init_error"},
                    status=500,
                )

        def _handle_audio_panic(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            try:
                audio_service = get_audio_service()
                audio_service.panic()
                self._send_json({"ok": True, "status": audio_service.status()})
            except Exception as exc:
                self._send_json(
                    {"error": f"Audio panic failed: {exc}", "reason": "init_error"},
                    status=500,
                )

        def _handle_audio_install_runtime(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            with runtime_install_lock:
                if runtime_install_job["running"]:
                    self._send_json({"started": False, "reason": "already_running"}, status=409)
                    return
                runtime_install_job.update(
                    {"running": True, "stage": "Starting…", "pct": 0, "result": None, "error": None}
                )
            thread = threading.Thread(target=run_runtime_install, daemon=True)
            thread.start()
            self._send_json({"started": True})

    return Handler
