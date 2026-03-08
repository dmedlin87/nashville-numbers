from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from http.client import HTTPConnection
import types
from typing import Any

import pytest

from nashville_numbers.audio import AudioInstallError, AudioUnavailableError
from nashville_numbers.music_lab import build_progression_plan
from nashville_numbers.tone_library import ToneLibrary
import nashville_numbers.gui as gui


class _FakeAudioService:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.raise_for: dict[str, Exception] = {}
        self.status_payload: dict[str, Any] = {
            "hq_ready": False,
            "engine": "unavailable",
            "reason": "missing_soundfont",
            "fallback": "web_tone",
            "pack": {"id": "fluidr3_gm", "installed": False, "path": None},
        }

    def status(self) -> dict[str, Any]:
        self.calls.append(("status",))
        return dict(self.status_payload)

    def install_default_pack(self) -> dict[str, Any]:
        self.calls.append(("install_default_pack",))
        exc = self.raise_for.get("install_default_pack")
        if exc:
            raise exc
        self.status_payload["hq_ready"] = True
        self.status_payload["engine"] = "fluidsynth"
        self.status_payload["reason"] = "ok"
        self.status_payload["pack"] = {
            "id": "fluidr3_gm",
            "installed": True,
            "path": "C:/tmp/FluidR3_GM.sf2",
        }
        return dict(self.status_payload)

    def play_note(self, midi: int, *, velocity: int, duration_ms: int, channel: int) -> None:
        self.calls.append(("play_note", midi, velocity, duration_ms, channel))
        exc = self.raise_for.get("play_note")
        if exc:
            raise exc

    def note_on(self, midi: int, *, velocity: int, channel: int) -> None:
        self.calls.append(("note_on", midi, velocity, channel))
        exc = self.raise_for.get("note_on")
        if exc:
            raise exc

    def note_off(self, midi: int, *, channel: int) -> None:
        self.calls.append(("note_off", midi, channel))
        exc = self.raise_for.get("note_off")
        if exc:
            raise exc

    def play_chord(
        self,
        midis: list[int],
        *,
        style: str,
        strum_ms: int,
        note_ms: int,
        velocity: int,
        channel: int,
    ) -> None:
        self.calls.append(("play_chord", midis, style, strum_ms, note_ms, velocity, channel))
        exc = self.raise_for.get("play_chord")
        if exc:
            raise exc

    def play_sequence(self, events: list[dict[str, Any]], *, reset: bool) -> None:
        self.calls.append(("play_sequence", events, reset))
        exc = self.raise_for.get("play_sequence")
        if exc:
            raise exc

    def panic(self) -> None:
        self.calls.append(("panic",))
        exc = self.raise_for.get("panic")
        if exc:
            raise exc

    def install_runtime(self, on_progress=None) -> dict[str, Any]:
        self.calls.append(("install_runtime",))
        exc = self.raise_for.get("install_runtime")
        if exc:
            raise exc
        return {
            "runtime_binary": True,
            "python_binding": True,
            "ready": True,
            "message": "FluidSynth runtime and Python binding are ready.",
            "audio_status": dict(self.status_payload),
        }


@pytest.fixture
def gui_server() -> int:
    server = gui._DEFAULT_APP.create_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _host, port = server.server_address
    _AUTH_PORT["port"] = port
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)


def _request(
    port: int,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        payload = response.read().decode("utf-8")
        return response.status, {k.lower(): v for k, v in response.getheaders()}, payload
    finally:
        conn.close()


_AUTH_PORT: dict[str, int] = {"port": 0}


def _auth_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    probe = HTTPConnection("127.0.0.1", _AUTH_PORT["port"], timeout=3)
    try:
        probe.request("GET", "/")
        response = probe.getresponse()
        response.read()
        cookie = response.getheader("Set-Cookie") or ""
    finally:
        probe.close()
    merged = {"Cookie": cookie.split(";", 1)[0]}
    if headers:
        merged.update(headers)
    return merged


def _post_json(
    port: int, path: str, payload: Any, *, authenticated: bool = True
) -> tuple[int, dict[str, str], dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if authenticated:
        _AUTH_PORT["port"] = port
        headers = _auth_headers(headers)
    status, headers, text = _request(
        port,
        "POST",
        path,
        body=body,
        headers=headers,
    )
    return status, headers, json.loads(text)


def _post_multipart(
    port: int,
    path: str,
    *,
    filename: str,
    file_bytes: bytes,
    fields: dict[str, str] | None = None,
    content_type_extra: str = "",
    authenticated: bool = True,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    boundary = f"----nns-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in (fields or {}).items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    extra = f"; {content_type_extra}" if content_type_extra else ""
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}{extra}"}
    if authenticated:
        _AUTH_PORT["port"] = port
        headers = _auth_headers(headers)
    status, headers, text = _request(port, "POST", path, body=body, headers=headers)
    return status, headers, json.loads(text)


def _get_json(
    port: int, path: str, *, authenticated: bool = True
) -> tuple[int, dict[str, str], dict[str, Any]]:
    _AUTH_PORT["port"] = port
    headers = _auth_headers() if authenticated else None
    status, headers, text = _request(port, "GET", path, headers=headers)
    return status, headers, json.loads(text)


def _poll_until_done(port: int, *, timeout: float = 3.0, interval: float = 0.05) -> dict[str, Any]:
    """Poll /audio/install-runtime/status until running is False, then return the job dict."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, _, job = _get_json(port, "/audio/install-runtime/status")
        if not job.get("running"):
            return job
        time.sleep(interval)
    raise TimeoutError("Runtime install job did not finish in time")


def _poll_until_done_default(port: int, *, timeout: float = 3.0, interval: float = 0.05) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, _, job = _get_json(port, "/audio/install-default/status")
        if not job.get("running"):
            return job
        time.sleep(interval)
    raise TimeoutError("Default install job did not finish in time")


@pytest.fixture(autouse=True)
def reset_runtime_install_job() -> None:
    """Reset the global job state before every test to prevent state leakage."""
    gui._DEFAULT_APP._audio_service = None
    gui._DEFAULT_APP._tone_library = None
    gui._DEFAULT_APP.handler_class = None
    with gui._DEFAULT_APP.install_job_lock:
        gui._DEFAULT_APP.runtime_install_job.update(
            {"id": "", "running": False, "stage": "", "pct": 0, "result": None, "error": None}
        )
        gui._DEFAULT_APP.default_install_job.update(
            {"id": "", "running": False, "stage": "", "pct": 0, "result": None, "error": None}
        )


@pytest.fixture
def tone_library_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path) -> ToneLibrary:
    library = ToneLibrary(root_dir=tmp_path / "tones")
    monkeypatch.setattr(gui._DEFAULT_APP, "_tone_library", library)
    return library


@pytest.fixture
def fake_audio_service(monkeypatch: pytest.MonkeyPatch) -> _FakeAudioService:
    service = _FakeAudioService()
    monkeypatch.setattr(gui._DEFAULT_APP, "_audio_service", service)
    return service


def test_handler_class_is_built_lazily_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[dict[str, Any]] = []

    class SentinelHandler:
        pass

    def fake_build_handler(**kwargs: Any) -> type:
        built.append(kwargs)
        return SentinelHandler

    monkeypatch.setattr(gui, "build_handler", fake_build_handler)

    assert built == []
    assert gui._DEFAULT_APP.get_handler_class() is SentinelHandler
    assert len(built) == 1
    assert gui._DEFAULT_APP.get_handler_class() is SentinelHandler
    assert len(built) == 1


def test_get_root_serves_embedded_html(gui_server: int) -> None:
    status, headers, body = _request(gui_server, "GET", "/")
    assert status == 200
    assert "text/html" in headers["content-type"]
    assert "<title>Nashville Numbers</title>" in body
    assert 'meta name="nns-request-token"' not in body
    assert "set-cookie" in headers


def test_get_unknown_path_returns_not_found_json(gui_server: int) -> None:
    status, headers, body = _request(gui_server, "GET", "/does-not-exist")
    assert status == 404
    assert "application/json" in headers["content-type"]
    assert json.loads(body) == {"error": "not found"}


def test_get_audio_status_returns_current_audio_state(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    status, headers, body = _request(gui_server, "GET", "/audio/status", headers=_auth_headers())
    assert status == 200
    assert "application/json" in headers["content-type"]
    payload = json.loads(body)
    assert payload["hq_ready"] is False
    assert payload["reason"] == "missing_soundfont"
    assert payload["fallback"] == "web_tone"
    assert fake_audio_service.calls == [("status",)]


def test_get_audio_status_requires_session(gui_server: int) -> None:
    status, _headers, payload = _get_json(gui_server, "/audio/status", authenticated=False)
    assert status == 403
    assert payload == {"error": "Forbidden", "reason": "session_invalid"}


def test_get_tone_library_requires_session(gui_server: int, tone_library_tmp: ToneLibrary) -> None:
    status, _headers, payload = _get_json(gui_server, "/tone/library", authenticated=False)
    assert status == 403
    assert payload == {"error": "Forbidden", "reason": "session_invalid"}


def test_get_tone_library_returns_empty_payload(
    gui_server: int, tone_library_tmp: ToneLibrary
) -> None:
    status, _headers, payload = _get_json(gui_server, "/tone/library")
    assert status == 200
    assert payload["ok"] is True
    assert payload["library"]["tones"] == []
    assert payload["library"]["irs"] == []


def test_post_tone_import_model_and_remove_updates_library(
    gui_server: int, tone_library_tmp: ToneLibrary
) -> None:
    model = (
        b'{'
        b'"name":"Twin Clean",'
        b'"version":"0.9.0",'
        b'"architecture":"wavenet",'
        b'"sample_rate":48000,'
        b'"weights":[1,2,3]'
        b'}'
    )
    status, _headers, payload = _post_multipart(
        gui_server,
        "/tone/import-model",
        filename="twin.nam",
        file_bytes=model,
    )
    assert status == 200
    assert payload["ok"] is True
    tone = payload["tone"]
    assert tone["name"] == "Twin Clean"
    assert tone["compatibility"] == "compatible"
    assert tone["metadata"]["architecture"] == "wavenet"

    status, _headers, payload = _post_json(
        gui_server,
        "/tone/remove",
        {"tone_id": tone["id"]},
    )
    assert status == 200
    assert payload["ok"] is True
    assert payload["removed_id"] == tone["id"]
    assert payload["library"]["tones"] == []


def test_post_tone_import_model_rejects_invalid_format(
    gui_server: int, tone_library_tmp: ToneLibrary
) -> None:
    status, _headers, payload = _post_multipart(
        gui_server,
        "/tone/import-model",
        filename="bad.nam",
        file_bytes=b"not-json",
    )
    assert status == 415
    assert payload["reason"] == "invalid_model_format"


def test_post_tone_import_ir_attach_and_detach(
    gui_server: int, tone_library_tmp: ToneLibrary
) -> None:
    model = b'{"version":"0.8","architecture":"unknown-arch","weights":[]}'
    status, _headers, payload = _post_multipart(
        gui_server,
        "/tone/import-model",
        filename="amp.nam",
        file_bytes=model,
    )
    assert status == 200
    tone_id = payload["tone"]["id"]
    assert payload["tone"]["compatibility"] == "warning"

    status, _headers, payload = _post_multipart(
        gui_server,
        "/tone/import-ir",
        filename="cab.wav",
        file_bytes=b"RIFF....WAVEfmt ",
        fields={"tone_id": tone_id},
    )
    assert status == 200
    assert payload["ok"] is True
    ir_id = payload["ir"]["id"]
    assert payload["tone"]["ir_id"] == ir_id

    status, _headers, payload = _post_json(
        gui_server,
        "/tone/attach-ir",
        {"tone_id": tone_id, "ir_id": None},
    )
    assert status == 200
    assert payload["ok"] is True
    assert payload["tone"]["ir_file"] is None


def test_post_tone_import_rejects_wrong_extension(
    gui_server: int, tone_library_tmp: ToneLibrary
) -> None:
    status, _headers, payload = _post_multipart(
        gui_server,
        "/tone/import-ir",
        filename="cab.mp3",
        file_bytes=b"fake",
    )
    assert status == 415
    assert payload["reason"] == "invalid_extension"


def test_post_tone_import_requires_session(gui_server: int, tone_library_tmp: ToneLibrary) -> None:
    status, _headers, payload = _post_multipart(
        gui_server,
        "/tone/import-model",
        filename="ok.nam",
        file_bytes=b'{"version":"0.9","architecture":"wavenet","weights":[]}',
        authenticated=False,
    )
    assert status == 403
    assert payload == {"error": "Forbidden", "reason": "session_invalid"}


def test_post_tone_import_model_accepts_content_type_with_extra_params(
    gui_server: int, tone_library_tmp: ToneLibrary
) -> None:
    status, _headers, payload = _post_multipart(
        gui_server,
        "/tone/import-model",
        filename="ok.nam",
        file_bytes=b'{"version":"0.9","architecture":"wavenet","weights":[]}',
        content_type_extra="charset=utf-8",
    )
    assert status == 200
    assert payload["ok"] is True


def test_post_tone_import_ir_preserves_uploaded_file_bytes(
    gui_server: int, tone_library_tmp: ToneLibrary
) -> None:
    data = b"\nRIFF....WAVEfmt \x00 trailing-space "
    status, _headers, payload = _post_multipart(
        gui_server,
        "/tone/import-ir",
        filename="cab.wav",
        file_bytes=data,
    )
    assert status == 200
    ir_file = payload["ir"]["file"]
    assert (tone_library_tmp.irs_dir / ir_file).read_bytes() == data


def test_post_audio_install_default_success_returns_status(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    status, _headers, payload = _post_json(gui_server, "/audio/install-default", {})
    assert status == 200
    assert payload["started"] is True
    job = _poll_until_done_default(gui_server)
    assert job["result"]["hq_ready"] is True
    assert job["result"]["engine"] == "fluidsynth"
    assert job["result"]["pack"]["installed"] is True


def test_post_audio_install_default_unavailable_returns_conflict(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    fake_audio_service.raise_for["install_default_pack"] = AudioUnavailableError("disabled", "Audio disabled")
    status, _headers, payload = _post_json(gui_server, "/audio/install-default", {})
    assert status == 200
    assert payload["started"] is True
    job = _poll_until_done_default(gui_server)
    assert job["error"] == "Audio disabled"


def test_post_audio_install_default_failure_returns_server_error(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    fake_audio_service.raise_for["install_default_pack"] = AudioInstallError("download_failed", "network")
    status, _headers, payload = _post_json(gui_server, "/audio/install-default", {})
    assert status == 200
    assert payload["started"] is True
    job = _poll_until_done_default(gui_server)
    assert job["error"] == "network"


def test_post_audio_install_runtime_returns_started_immediately(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    status, _headers, payload = _post_json(gui_server, "/audio/install-runtime", {})
    assert status == 200
    assert payload["started"] is True
    assert payload["job"]["id"]


def test_get_install_runtime_status_returns_job_state(gui_server: int) -> None:
    _, _, job = _get_json(gui_server, "/audio/install-runtime/status")
    assert "running" in job
    assert "pct" in job
    assert "stage" in job


def test_post_audio_install_runtime_job_completes_with_result(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    _post_json(gui_server, "/audio/install-runtime", {})
    job = _poll_until_done(gui_server)
    assert job["running"] is False
    assert job["result"]["ready"] is True
    assert job["result"]["audio_status"] is not None
    assert ("install_runtime",) in fake_audio_service.calls


def test_post_audio_install_runtime_job_records_error_on_exception(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    fake_audio_service.raise_for["install_runtime"] = RuntimeError("install crashed")
    _post_json(gui_server, "/audio/install-runtime", {})
    job = _poll_until_done(gui_server)
    assert job["running"] is False
    assert job["result"] is None
    assert "install crashed" in (job["error"] or "")


def test_post_audio_install_runtime_rejects_concurrent_request(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    with gui._DEFAULT_APP.install_job_lock:
        gui._DEFAULT_APP.runtime_install_job["running"] = True
    try:
        status, _headers, payload = _post_json(gui_server, "/audio/install-runtime", {})
        assert status == 503
        assert payload["reason"] == "install_in_progress"
    finally:
        with gui._DEFAULT_APP.install_job_lock:
            gui._DEFAULT_APP.runtime_install_job["running"] = False


def test_post_convert_success_returns_result(gui_server: int, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_convert(text: str) -> str:
        calls.append(text)
        return "Key: C Major\n1 4 5"

    monkeypatch.setattr(gui, "convert", fake_convert)

    status, _headers, payload = _post_json(gui_server, "/convert", {"input": "C F G"})

    assert status == 200
    assert payload == {"result": "Key: C Major\n1 4 5"}
    assert calls == ["C F G"]


def test_post_convert_rejects_invalid_json(gui_server: int) -> None:
    status, _headers, body = _request(
        gui_server,
        "POST",
        "/convert",
        body=b"{not-json",
        headers=_auth_headers({"Content-Type": "application/json"}),
    )
    assert status == 400
    assert json.loads(body) == {"error": "Invalid JSON in request body"}


def test_post_convert_requires_json_object(gui_server: int) -> None:
    status, _headers, payload = _post_json(gui_server, "/convert", ["C F G"])
    assert status == 400
    assert payload == {"error": "Expected JSON object"}


def test_post_convert_rejects_empty_input(gui_server: int) -> None:
    status, _headers, payload = _post_json(gui_server, "/convert", {"input": "   "})
    assert status == 200
    assert payload == {"error": "Empty input"}


def test_post_convert_requires_session(gui_server: int) -> None:
    status, _headers, payload = _post_json(
        gui_server, "/convert", {"input": "C F G"}, authenticated=False
    )
    assert status == 403
    assert payload == {"error": "Forbidden", "reason": "session_invalid"}


def test_post_arrangement_plan_returns_structured_plan(
    gui_server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_plan(input_text: str, **kwargs: Any) -> dict[str, Any]:
        assert input_text == "C - Am - F - G"
        assert kwargs["tempo"] == 104
        return {
            "tempo": kwargs["tempo"],
            "meter": kwargs["meter"],
            "count_in_beats": kwargs["count_in_beats"],
            "summary": {"bar_count": 4},
            "sections": [],
        }

    monkeypatch.setattr(gui, "build_progression_plan", fake_plan)

    status, _headers, payload = _post_json(
        gui_server,
        "/arrangement/plan",
        {
            "input": "C - Am - F - G",
            "tempo": 104,
            "meter": 4,
            "count_in_beats": 4,
            "groove": "anthem",
            "bass_enabled": True,
        },
    )

    assert status == 200
    assert payload["plan"]["tempo"] == 104
    assert payload["plan"]["summary"]["bar_count"] == 4


def test_post_arrangement_plan_validates_boolean_flag(gui_server: int) -> None:
    status, _headers, payload = _post_json(
        gui_server,
        "/arrangement/plan",
        {"input": "C - F - G", "bass_enabled": "yes"},
    )

    assert status == 400
    assert payload["reason"] == "validation"
    assert payload["error"] == "'bass_enabled' must be a boolean"


def test_post_convert_enforces_payload_size_limit(gui_server: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gui, "MAX_INPUT_LENGTH", 10)
    status, _headers, body = _request(
        gui_server,
        "POST",
        "/convert",
        body=b"",
        headers=_auth_headers({"Content-Type": "application/json", "Content-Length": "11"}),
    )
    payload = json.loads(body)
    assert status == 413
    assert payload == {"error": "Payload too large"}


def test_post_convert_handles_known_converter_errors(
    gui_server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_value_error(_text: str) -> str:
        raise ValueError("bad conversion")

    monkeypatch.setattr(gui, "convert", raise_value_error)
    status, _headers, payload = _post_json(gui_server, "/convert", {"input": "C"})
    assert status == 200
    assert payload == {"error": "bad conversion"}


def test_post_audio_play_note_calls_service(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    status, _headers, payload = _post_json(
        gui_server,
        "/audio/play-note",
        {"midi": 60, "velocity": 110, "duration_ms": 320, "channel": 1},
    )
    assert status == 200
    assert payload["ok"] is True
    assert ("play_note", 60, 110, 320, 1) in fake_audio_service.calls


def test_post_audio_play_note_returns_conflict_when_hq_unavailable(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    fake_audio_service.raise_for["play_note"] = AudioUnavailableError("missing_soundfont", "HQ unavailable")
    status, _headers, payload = _post_json(gui_server, "/audio/play-note", {"midi": 60})
    assert status == 409
    assert payload == {"error": "HQ unavailable", "reason": "missing_soundfont"}


def test_post_audio_play_note_validates_range(gui_server: int) -> None:
    status, _headers, payload = _post_json(gui_server, "/audio/play-note", {"midi": 220})
    assert status == 400
    assert payload["reason"] == "validation"
    assert "'midi' must be between 0 and 127" in payload["error"]


def test_post_audio_note_on_validates_range(gui_server: int) -> None:
    status, _headers, payload = _post_json(gui_server, "/audio/note-on", {"midi": -1})
    assert status == 400
    assert payload["reason"] == "validation"
    assert "'midi' must be between 0 and 127" in payload["error"]


def test_post_audio_note_off_validates_range(gui_server: int) -> None:
    status, _headers, payload = _post_json(gui_server, "/audio/note-off", {"midi": 5, "channel": 99})
    assert status == 400
    assert payload["reason"] == "validation"
    assert "'channel' must be between 0 and 15" in payload["error"]


def test_post_audio_play_chord_validates_input(gui_server: int) -> None:
    status, _headers, payload = _post_json(gui_server, "/audio/play-chord", {"midis": [60], "style": "arp"})
    assert status == 400
    assert payload["reason"] == "validation"
    assert payload["error"] == "'style' must be 'block' or 'strum'"


def test_post_audio_play_sequence_calls_service(
    gui_server: int, fake_audio_service: _FakeAudioService
) -> None:
    status, _headers, payload = _post_json(
        gui_server,
        "/audio/play-sequence",
        {
            "events": [
                {"kind": "note", "delay_ms": 0, "midi": 60, "duration_ms": 300},
                {"kind": "chord", "delay_ms": 120, "midis": [60, 64, 67], "duration_ms": 700},
            ],
            "reset": True,
        },
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["queued"] == 2
    assert fake_audio_service.calls[-2][0] == "play_sequence"
    assert fake_audio_service.calls[-2][2] is True


def test_post_audio_play_sequence_validates_kind(gui_server: int) -> None:
    status, _headers, payload = _post_json(
        gui_server,
        "/audio/play-sequence",
        {"events": [{"kind": "noise", "delay_ms": 0, "duration_ms": 100}]},
    )

    assert status == 400
    assert payload["reason"] == "validation"
    assert payload["error"] == "Each event 'kind' must be 'note' or 'chord'"


def test_post_audio_panic_requires_json_object(gui_server: int) -> None:
    status, _headers, payload = _post_json(gui_server, "/audio/panic", ["not-object"])
    assert status == 400
    assert payload == {"error": "Expected JSON object"}


def test_post_unknown_path_returns_404(gui_server: int) -> None:
    status, _headers, body = _request(gui_server, "POST", "/nope")
    payload = json.loads(body)
    assert status == 404
    assert payload == {"error": "not found"}


def test_find_free_port_skips_port_in_use() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        start = busy.getsockname()[1]
        found = gui._DEFAULT_APP.find_free_port(start=start)
        assert found != start
        assert start < found <= start + 100


def test_find_free_port_raises_when_all_candidates_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    class AlwaysBusySocket:
        def __enter__(self) -> AlwaysBusySocket:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def bind(self, _addr: tuple[str, int]) -> None:
            raise OSError("busy")

    monkeypatch.setattr(gui.socket, "socket", lambda *_args, **_kwargs: AlwaysBusySocket())

    with pytest.raises(OSError, match="Unable to find an available port"):
        gui._DEFAULT_APP.find_free_port(start=9000)


def test_find_free_port_defaults_to_ephemeral_binding() -> None:
    assert gui._DEFAULT_APP.find_free_port() == 0


def test_start_server_uses_bound_port_for_ephemeral_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[bool] = []

    class FakeServer:
        server_address = ("127.0.0.1", 43210)

    class FakeThread:
        def start(self) -> None:
            started.append(True)

    fake_server = FakeServer()
    fake_thread = FakeThread()

    monkeypatch.setattr(gui._DEFAULT_APP, "create_server", lambda port: fake_server)
    monkeypatch.setattr(gui._DEFAULT_APP, "create_thread", lambda target, args, daemon: fake_thread)

    server, url, thread = gui._DEFAULT_APP.start_server(0)

    assert server is fake_server
    assert url == "http://127.0.0.1:43210"
    assert thread is fake_thread
    assert started == [True]


def test_start_server_swallows_unexpected_errors() -> None:
    class BoomServer:
        def serve_forever(self) -> None:
            raise RuntimeError("boom")

    gui._DEFAULT_APP.serve_server(BoomServer())


def test_html_contains_builder_placeholder_guard() -> None:
    assert "function ensureProgressionEmptyNode()" in gui._HTML
    assert "const empty = ensureProgressionEmptyNode();" in gui._HTML


def test_main_uses_native_window_when_webview_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    port = 9876
    opened: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    webview_started: list[bool] = []
    threads: list[Any] = []

    class FakeServer:
        def __init__(self) -> None:
            self.serve_forever_calls = 0
            self.shutdown_calls = 0
            self.close_calls = 0

        def serve_forever(self) -> None:
            self.serve_forever_calls += 1

        def shutdown(self) -> None:
            self.shutdown_calls += 1

        def server_close(self) -> None:
            self.close_calls += 1

    class FakeThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.started = False
            self.joined = False
            self.timeout: float | None = None
            threads.append(self)

        def start(self) -> None:
            self.started = True
            self.target(*self.args)

        def join(self, timeout: float | None = None) -> None:
            self.joined = True
            self.timeout = timeout

    fake_server = FakeServer()

    monkeypatch.setattr(gui._DEFAULT_APP, "find_free_port", lambda: port)
    monkeypatch.setattr(gui._DEFAULT_APP, "create_http_server", lambda _port, _handler: fake_server)
    monkeypatch.setattr(gui._DEFAULT_APP, "create_thread", lambda target, args, daemon: FakeThread(target, args, daemon))

    fake_webview = types.SimpleNamespace(
        create_window=lambda *args, **kwargs: opened.append((args, kwargs)),
        start=lambda: webview_started.append(True),
    )
    monkeypatch.setattr(gui._DEFAULT_APP, "import_webview", lambda: fake_webview)

    gui.main()

    assert opened
    args, kwargs = opened[0]
    assert args[0] == "Nashville Numbers"
    assert args[1] == f"http://127.0.0.1:{port}"
    assert kwargs["width"] == 1440
    assert kwargs["height"] == 900
    assert kwargs["min_size"] == (680, 540)
    assert webview_started == [True]
    assert fake_server.serve_forever_calls == 1
    assert fake_server.shutdown_calls == 1
    assert fake_server.close_calls == 1
    assert len(threads) == 1
    assert threads[0].started is True
    assert threads[0].joined is True
    assert threads[0].timeout == 1.0


def test_main_falls_back_to_browser_when_webview_import_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    port = 9988
    opened_urls: list[str] = []
    threads: list[Any] = []

    class FakeServer:
        def __init__(self) -> None:
            self.shutdown_calls = 0
            self.close_calls = 0

        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            self.shutdown_calls += 1

        def server_close(self) -> None:
            self.close_calls += 1

    class FakeThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.joined = False
            self.timeout: float | None = None
            threads.append(self)

        def start(self) -> None:
            self.target(*self.args)

        def join(self, timeout: float | None = None) -> None:
            self.joined = True
            self.timeout = timeout

    class FakeTimer:
        def __init__(self, _interval: float, callback: Any) -> None:
            self.callback = callback

        def start(self) -> None:
            self.callback()

    class FakeEvent:
        def wait(self, _seconds: float) -> None:
            raise KeyboardInterrupt

    fake_server = FakeServer()
    monkeypatch.setattr(gui._DEFAULT_APP, "find_free_port", lambda: port)
    monkeypatch.setattr(gui._DEFAULT_APP, "create_http_server", lambda _port, _handler: fake_server)
    monkeypatch.setattr(gui._DEFAULT_APP, "create_thread", lambda target, args, daemon: FakeThread(target, args, daemon))
    monkeypatch.setattr(gui._DEFAULT_APP, "create_timer", lambda _interval, callback: FakeTimer(_interval, callback))
    monkeypatch.setattr(gui._DEFAULT_APP, "create_event", lambda: FakeEvent())
    monkeypatch.setattr(gui._DEFAULT_APP, "open_browser", lambda url: opened_urls.append(url))
    monkeypatch.setattr(
        gui._DEFAULT_APP,
        "import_webview",
        lambda: (_ for _ in ()).throw(ImportError("missing webview")),
    )

    gui.main()

    out = capsys.readouterr().out
    assert "pywebview not installed. Falling back to default browser." in out
    assert "Press Ctrl-C to stop." in out
    assert "Stopped." in out
    assert opened_urls == [f"http://127.0.0.1:{port}"]
    assert fake_server.shutdown_calls == 1
    assert fake_server.close_calls == 1
    assert len(threads) == 1
    assert threads[0].joined is True
    assert threads[0].timeout == 1.0


def test_main_falls_back_to_browser_when_webview_runtime_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    port = 9989
    opened_urls: list[str] = []

    class FakeServer:
        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

        def server_close(self) -> None:
            return None

    class FakeThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            self.target(*self.args)

        def join(self, timeout: float | None = None) -> None:
            return None

    class FakeTimer:
        def __init__(self, _interval: float, callback: Any) -> None:
            self.callback = callback

        def start(self) -> None:
            self.callback()

    class FakeEvent:
        def wait(self, _seconds: float) -> None:
            raise KeyboardInterrupt

    fake_webview = types.SimpleNamespace(
        create_window=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        start=lambda: None,
    )

    monkeypatch.setattr(gui._DEFAULT_APP, "import_webview", lambda: fake_webview)
    monkeypatch.setattr(gui._DEFAULT_APP, "find_free_port", lambda: port)
    monkeypatch.setattr(gui._DEFAULT_APP, "create_http_server", lambda _port, _handler: FakeServer())
    monkeypatch.setattr(gui._DEFAULT_APP, "create_thread", lambda target, args, daemon: FakeThread(target, args, daemon))
    monkeypatch.setattr(gui._DEFAULT_APP, "create_timer", lambda _interval, callback: FakeTimer(_interval, callback))
    monkeypatch.setattr(gui._DEFAULT_APP, "create_event", lambda: FakeEvent())
    monkeypatch.setattr(gui._DEFAULT_APP, "open_browser", lambda url: opened_urls.append(url))

    gui.main()

    out = capsys.readouterr().out
    assert "Failed to start native window: boom. Falling back to default browser." in out
    assert opened_urls == [f"http://127.0.0.1:{port}"]


# ---------------------------------------------------------------------------
# Arrangement export-midi endpoint
# ---------------------------------------------------------------------------


def _post_raw(
    port: int, path: str, payload: Any, *, authenticated: bool = True
) -> tuple[int, dict[str, str], bytes]:
    """POST JSON and return the raw response body as bytes (not parsed as JSON)."""
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if authenticated:
        _AUTH_PORT["port"] = port
        headers = _auth_headers(headers)
    conn = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, raw
    finally:
        conn.close()


def test_post_arrangement_export_midi_returns_midi_file(gui_server: int) -> None:
    payload = {"input": "C - Am - F - G", "tempo": 120, "groove": "anthem"}
    status, headers, body = _post_raw(gui_server, "/arrangement/export-midi", payload)
    assert status == 200
    assert headers["content-type"] == "audio/midi"
    assert "arrangement.mid" in headers.get("content-disposition", "")
    assert body[:4] == b"MThd"
    assert len(body) > 50


def test_post_arrangement_export_midi_empty_input(gui_server: int) -> None:
    payload = {"input": ""}
    status, _, body = _post_raw(gui_server, "/arrangement/export-midi", payload)
    data = json.loads(body)
    assert "error" in data


def test_post_arrangement_export_midi_requires_session(gui_server: int) -> None:
    status, _, body = _post_raw(
        gui_server, "/arrangement/export-midi", {"input": "C - F - G"}, authenticated=False
    )
    data = json.loads(body)
    assert status == 403
    assert data.get("error") == "Forbidden"


# ---------------------------------------------------------------------------
# voicing_style and voice_leading HTTP passthrough
# ---------------------------------------------------------------------------


def test_post_arrangement_plan_passes_voicing_params(
    gui_server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_plan(input_text: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "tempo": kwargs["tempo"],
            "meter": kwargs["meter"],
            "count_in_beats": kwargs["count_in_beats"],
            "summary": {"bar_count": 4},
            "sections": [],
        }

    monkeypatch.setattr(gui, "build_progression_plan", fake_plan)

    status, _headers, payload = _post_json(
        gui_server,
        "/arrangement/plan",
        {
            "input": "C - Am - F - G",
            "voicing_style": "drop2",
            "voice_leading": True,
        },
    )

    assert status == 200
    assert captured["voicing_style"] == "drop2"
    assert captured["voice_leading"] is True


def test_post_arrangement_plan_voicing_defaults(
    gui_server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_plan(input_text: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "tempo": kwargs["tempo"],
            "meter": kwargs["meter"],
            "count_in_beats": kwargs["count_in_beats"],
            "summary": {"bar_count": 4},
            "sections": [],
        }

    monkeypatch.setattr(gui, "build_progression_plan", fake_plan)

    status, _headers, payload = _post_json(
        gui_server,
        "/arrangement/plan",
        {"input": "C - Am - F - G"},
    )

    assert status == 200
    assert captured["voicing_style"] == "close"
    assert captured["voice_leading"] is False


def test_post_arrangement_plan_invalid_voicing_style(gui_server: int) -> None:
    status, _headers, payload = _post_json(
        gui_server,
        "/arrangement/plan",
        {"input": "C - F - G", "voicing_style": "bad"},
    )
    assert status == 400
    assert payload["reason"] == "validation"
    assert "voicing_style" in payload["error"]


def test_post_arrangement_plan_invalid_voice_leading(gui_server: int) -> None:
    status, _headers, payload = _post_json(
        gui_server,
        "/arrangement/plan",
        {"input": "C - F - G", "voice_leading": "yes"},
    )
    assert status == 400
    assert payload["reason"] == "validation"
    assert "voice_leading" in payload["error"]


def test_post_arrangement_export_midi_passes_voicing_params(
    gui_server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_plan(input_text: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return build_progression_plan(input_text, **kwargs)

    monkeypatch.setattr(gui, "build_progression_plan", fake_plan)

    status, headers, _ = _post_raw(
        gui_server,
        "/arrangement/export-midi",
        {"input": "C - F - G", "voicing_style": "drop3", "voice_leading": True},
    )

    assert status == 200
    assert captured["voicing_style"] == "drop3"
    assert captured["voice_leading"] is True
