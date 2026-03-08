"""HTTP request handling for the embedded GUI."""

from __future__ import annotations

import json
import logging
import secrets
import threading
from contextlib import contextmanager
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from .audio import AudioInstallError, AudioUnavailableError

LOG = logging.getLogger(__name__)

_VOICING_STYLES = {"close", "drop2", "drop3"}


def build_handler(
    *,
    get_html: Callable[[], str],
    get_session_cookie_name: Callable[[], str],
    get_expected_session_value: Callable[[], str],
    issue_session_cookie: Callable[[], str],
    is_allowed_origin: Callable[[str | None, str | None], bool],
    conversion_semaphore: threading.BoundedSemaphore,
    get_audio_service: Callable[[], Any],
    convert_text: Callable[[str], str],
    plan_arrangement: Callable[..., dict[str, Any]],
    get_max_input_length: Callable[[], int],
    default_install_job: dict[str, Any],
    runtime_install_job: dict[str, Any],
    install_job_lock: threading.Lock,
    run_default_pack_install: Callable[[], None],
    run_runtime_install: Callable[[], None],
) -> type[BaseHTTPRequestHandler]:
    protected_get_paths = {"/audio/status", "/audio/install-default/status", "/audio/install-runtime/status"}
    protected_post_paths = {
        "/convert",
        "/arrangement/plan",
        "/arrangement/export-midi",
        "/audio/install-default",
        "/audio/play-note",
        "/audio/note-on",
        "/audio/note-off",
        "/audio/play-chord",
        "/audio/play-sequence",
        "/audio/panic",
        "/audio/install-runtime",
    }

    class Handler(BaseHTTPRequestHandler):
        """Minimal request handler serving the single-page app and a JSON API."""

        def log_message(self, format: str, *args: object) -> None:  # silence access logs
            pass

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in protected_get_paths and not self._require_session():
                return
            if parsed.path in ("/", "/index.html"):
                self._send_html(get_html(), cookie=issue_session_cookie())
            elif parsed.path == "/audio/status":
                self._send_json(get_audio_service().status())
            elif parsed.path == "/audio/install-default/status":
                with install_job_lock:
                    self._send_json(dict(default_install_job))
            elif parsed.path == "/audio/install-runtime/status":
                with install_job_lock:
                    self._send_json(dict(runtime_install_job))
            else:
                self._send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in protected_post_paths and not self._require_session(drain_body=True):
                return
            if parsed.path == "/convert":
                self._handle_convert()
                return
            if parsed.path == "/arrangement/plan":
                self._handle_arrangement_plan()
                return
            if parsed.path == "/arrangement/export-midi":
                self._handle_arrangement_export_midi()
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
            if parsed.path == "/audio/play-sequence":
                self._handle_audio_play_sequence()
                return
            if parsed.path == "/audio/panic":
                self._handle_audio_panic()
                return
            if parsed.path == "/audio/install-runtime":
                self._handle_audio_install_runtime()
                return
            self._send_json({"error": "not found"}, status=404)

        def _send_html(self, html: str, *, cookie: str | None = None) -> None:
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, obj: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_binary(
            self,
            data: bytes,
            *,
            content_type: str,
            filename: str | None = None,
            status: int = 200,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if filename:
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{filename}"'
                )
            self.end_headers()
            self.wfile.write(data)

        def _drain_request_body(self) -> None:
            try:
                remaining = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    return
                remaining -= len(chunk)

        def _require_session(self, *, drain_body: bool = False) -> bool:
            origin = self.headers.get("Origin")
            referer = self.headers.get("Referer")
            if not is_allowed_origin(origin, referer):
                if drain_body:
                    self._drain_request_body()
                LOG.warning("Rejected GUI request due to origin mismatch: %s %s", origin, referer)
                self._send_json({"error": "Forbidden", "reason": "origin_rejected"}, status=403)
                return False
            expected = get_expected_session_value()
            cookie_name = get_session_cookie_name()
            cookie_header = self.headers.get("Cookie", "")
            provided = self._read_cookie(cookie_header, cookie_name)
            if provided is None or not secrets.compare_digest(provided, expected):
                if drain_body:
                    self._drain_request_body()
                LOG.warning("Rejected GUI request with invalid session cookie")
                self._send_json({"error": "Forbidden", "reason": "session_invalid"}, status=403)
                return False
            return True

        def _read_cookie(self, cookie_header: str, cookie_name: str) -> str | None:
            for chunk in cookie_header.split(";"):
                name, sep, value = chunk.strip().partition("=")
                if sep and name == cookie_name:
                    return value
            return None

        @contextmanager
        def _limited(self, semaphore: threading.BoundedSemaphore):
            if not semaphore.acquire(blocking=False):
                self._send_json({"error": "Too many active requests", "reason": "overloaded"}, status=429)
                yield False
                return
            try:
                yield True
            finally:
                semaphore.release()

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
            with self._limited(conversion_semaphore) as allowed:
                if not allowed:
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

        def _bool_field(self, payload: dict[str, Any], key: str, *, default: bool) -> bool:
            value = payload.get(key, default)
            if isinstance(value, bool):
                return value
            raise ValueError(f"'{key}' must be a boolean")

        def _handle_arrangement_plan(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            with self._limited(conversion_semaphore) as allowed:
                if not allowed:
                    return
                try:
                    input_text = str(payload.get("input", "")).strip()
                    if not input_text:
                        self._send_json({"error": "Empty input"})
                        return
                    tempo = self._int_field(payload, "tempo", minimum=40, maximum=220, default=96)
                    meter = self._int_field(payload, "meter", minimum=2, maximum=12, default=4)
                    count_in = self._int_field(payload, "count_in_beats", minimum=0, maximum=16, default=4)
                    groove = str(payload.get("groove", "anthem")).strip().lower() or "anthem"
                    bass_enabled = self._bool_field(payload, "bass_enabled", default=True)
                    voicing_style = str(payload.get("voicing_style", "close")).strip().lower()
                    if voicing_style not in _VOICING_STYLES:
                        raise ValueError(f"'voicing_style' must be one of {sorted(_VOICING_STYLES)}")
                    voice_leading = self._bool_field(payload, "voice_leading", default=False)
                    plan = plan_arrangement(
                        input_text,
                        tempo=tempo,
                        meter=meter,
                        groove=groove,
                        count_in_beats=count_in,
                        bass_enabled=bass_enabled,
                        voicing_style=voicing_style,
                        voice_leading=voice_leading,
                    )
                    self._send_json({"plan": plan})
                except ValueError as exc:
                    self._send_json({"error": str(exc), "reason": "validation"}, status=400)
                except Exception as exc:
                    self._send_json(
                        {"error": f"Failed to build arrangement: {exc}", "reason": "plan_failed"},
                        status=500,
                    )

        def _handle_arrangement_export_midi(self) -> None:
            from .midi_export import export_midi_bytes

            payload = self._read_json_payload()
            if payload is None:
                return
            with self._limited(conversion_semaphore) as allowed:
                if not allowed:
                    return
                try:
                    input_text = str(payload.get("input", "")).strip()
                    if not input_text:
                        self._send_json({"error": "Empty input"})
                        return
                    tempo = self._int_field(payload, "tempo", minimum=40, maximum=220, default=96)
                    meter = self._int_field(payload, "meter", minimum=2, maximum=12, default=4)
                    count_in = self._int_field(payload, "count_in_beats", minimum=0, maximum=16, default=4)
                    groove = str(payload.get("groove", "anthem")).strip().lower() or "anthem"
                    bass_enabled = self._bool_field(payload, "bass_enabled", default=True)
                    voicing_style = str(payload.get("voicing_style", "close")).strip().lower()
                    if voicing_style not in _VOICING_STYLES:
                        raise ValueError(f"'voicing_style' must be one of {sorted(_VOICING_STYLES)}")
                    voice_leading = self._bool_field(payload, "voice_leading", default=False)
                    plan = plan_arrangement(
                        input_text,
                        tempo=tempo,
                        meter=meter,
                        groove=groove,
                        count_in_beats=count_in,
                        bass_enabled=bass_enabled,
                        voicing_style=voicing_style,
                        voice_leading=voice_leading,
                    )
                    midi_bytes = export_midi_bytes(plan)
                    self._send_binary(
                        midi_bytes,
                        content_type="audio/midi",
                        filename="arrangement.mid",
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc), "reason": "validation"}, status=400)
                except Exception as exc:
                    self._send_json(
                        {"error": f"MIDI export failed: {exc}", "reason": "export_failed"},
                        status=500,
                    )

        def _handle_audio_install_default(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            with install_job_lock:
                if default_install_job["running"]:
                    self._send_json({"started": False, "reason": "install_in_progress"}, status=503)
                    return
                default_install_job.update(
                    {
                        "id": secrets.token_urlsafe(8),
                        "running": True,
                        "stage": "Starting…",
                        "pct": 0,
                        "result": None,
                        "error": None,
                    }
                )
            LOG.info("Starting default HQ pack install")
            thread = threading.Thread(target=run_default_pack_install, daemon=True)
            thread.start()
            self._send_json({"started": True, "job": dict(default_install_job)})

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

        def _handle_audio_play_sequence(self) -> None:
            payload = self._read_json_payload()
            if payload is None:
                return
            try:
                events_value = payload.get("events")
                if not isinstance(events_value, list):
                    raise ValueError("'events' must be an array")
                if not (1 <= len(events_value) <= 512):
                    raise ValueError("'events' must contain between 1 and 512 items")

                events: list[dict[str, Any]] = []
                for item in events_value:
                    if not isinstance(item, dict):
                        raise ValueError("Each event must be a JSON object")
                    kind = str(item.get("kind", "")).strip().lower()
                    delay_ms = self._int_field(item, "delay_ms", minimum=0, maximum=180000, default=0)
                    duration_ms = self._int_field(
                        item, "duration_ms", minimum=20, maximum=10000, default=700
                    )
                    velocity = self._int_field(item, "velocity", minimum=1, maximum=127, default=96)
                    channel = self._int_field(item, "channel", minimum=0, maximum=15, default=0)

                    if kind == "note":
                        midi = self._int_field(item, "midi", minimum=0, maximum=127, required=True)
                        events.append(
                            {
                                "kind": "note",
                                "delay_ms": delay_ms,
                                "duration_ms": duration_ms,
                                "velocity": velocity,
                                "channel": channel,
                                "midi": midi,
                            }
                        )
                        continue

                    if kind == "chord":
                        midis_value = item.get("midis")
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
                        style = str(item.get("style", "strum")).strip().lower()
                        if style not in {"block", "strum"}:
                            raise ValueError("'style' must be 'block' or 'strum'")
                        strum_ms = self._int_field(item, "strum_ms", minimum=0, maximum=120, default=28)
                        events.append(
                            {
                                "kind": "chord",
                                "delay_ms": delay_ms,
                                "duration_ms": duration_ms,
                                "velocity": velocity,
                                "channel": channel,
                                "midis": midis,
                                "style": style,
                                "strum_ms": strum_ms,
                            }
                        )
                        continue

                    raise ValueError("Each event 'kind' must be 'note' or 'chord'")

                reset = self._bool_field(payload, "reset", default=True)
                audio_service = get_audio_service()
                audio_service.play_sequence(events, reset=reset)
                self._send_json(
                    {"ok": True, "queued": len(events), "reset": reset, "status": audio_service.status()}
                )
            except ValueError as exc:
                self._send_json({"error": str(exc), "reason": "validation"}, status=400)
            except AudioUnavailableError as exc:
                self._send_json({"error": str(exc), "reason": exc.code}, status=409)
            except Exception as exc:
                self._send_json(
                    {"error": f"Audio sequence playback failed: {exc}", "reason": "init_error"},
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
            with install_job_lock:
                if runtime_install_job["running"]:
                    self._send_json({"started": False, "reason": "install_in_progress"}, status=503)
                    return
                runtime_install_job.update(
                    {
                        "id": secrets.token_urlsafe(8),
                        "running": True,
                        "stage": "Starting…",
                        "pct": 0,
                        "result": None,
                        "error": None,
                    }
                )
            LOG.info("Starting FluidSynth runtime install")
            thread = threading.Thread(target=run_runtime_install, daemon=True)
            thread.start()
            self._send_json({"started": True, "job": dict(runtime_install_job)})

    return Handler
