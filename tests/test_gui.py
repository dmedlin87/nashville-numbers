from __future__ import annotations

import json
import builtins
import socket
import threading
from http.client import HTTPConnection
import types
import sys
from typing import Any

import pytest

import nashville_numbers.gui as gui


@pytest.fixture
def gui_server() -> int:
    server = gui.HTTPServer(("127.0.0.1", 0), gui._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _host, port = server.server_address
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


def _post_json(port: int, path: str, payload: Any) -> tuple[int, dict[str, str], dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    status, headers, text = _request(
        port,
        "POST",
        path,
        body=body,
        headers={"Content-Type": "application/json"},
    )
    return status, headers, json.loads(text)


def test_get_root_serves_embedded_html(gui_server: int) -> None:
    status, headers, body = _request(gui_server, "GET", "/")
    assert status == 200
    assert "text/html" in headers["content-type"]
    assert "<title>Nashville Numbers</title>" in body


def test_get_unknown_path_returns_not_found_json(gui_server: int) -> None:
    status, headers, body = _request(gui_server, "GET", "/does-not-exist")
    assert status == 404
    assert "application/json" in headers["content-type"]
    assert json.loads(body) == {"error": "not found"}


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
        headers={"Content-Type": "application/json"},
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


def test_post_convert_enforces_payload_size_limit(gui_server: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gui, "MAX_INPUT_LENGTH", 10)
    status, _headers, body = _request(
        gui_server,
        "POST",
        "/convert",
        body=b"",
        headers={"Content-Type": "application/json", "Content-Length": "11"},
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


def test_post_unknown_path_returns_404(gui_server: int) -> None:
    status, _headers, body = _request(gui_server, "POST", "/nope")
    payload = json.loads(body)
    assert status == 404
    assert payload == {"error": "not found"}


def test_find_free_port_skips_port_in_use() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        start = busy.getsockname()[1]
        found = gui._find_free_port(start=start)
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
        gui._find_free_port(start=9000)


def test_start_server_swallows_unexpected_errors() -> None:
    class BoomServer:
        def serve_forever(self) -> None:
            raise RuntimeError("boom")

    gui._start_server(BoomServer())


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

    monkeypatch.setattr(gui, "_find_free_port", lambda: port)
    monkeypatch.setattr(gui, "HTTPServer", lambda _addr, _handler: fake_server)
    monkeypatch.setattr(gui.threading, "Thread", FakeThread)

    fake_webview = types.SimpleNamespace(
        create_window=lambda *args, **kwargs: opened.append((args, kwargs)),
        start=lambda: webview_started.append(True),
    )
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

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
    monkeypatch.setattr(gui, "_find_free_port", lambda: port)
    monkeypatch.setattr(gui, "HTTPServer", lambda _addr, _handler: fake_server)
    monkeypatch.setattr(gui.threading, "Thread", FakeThread)
    monkeypatch.setattr(gui.threading, "Timer", FakeTimer)
    monkeypatch.setattr(gui.threading, "Event", lambda: FakeEvent())
    monkeypatch.setattr(gui.webbrowser, "open", lambda url: opened_urls.append(url))

    real_import = builtins.__import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[no-untyped-def]
        if name == "webview":
            raise ImportError("missing webview")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

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

    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setattr(gui, "_find_free_port", lambda: port)
    monkeypatch.setattr(gui, "HTTPServer", lambda _addr, _handler: FakeServer())
    monkeypatch.setattr(gui.threading, "Thread", FakeThread)
    monkeypatch.setattr(gui.threading, "Timer", FakeTimer)
    monkeypatch.setattr(gui.threading, "Event", lambda: FakeEvent())
    monkeypatch.setattr(gui.webbrowser, "open", lambda url: opened_urls.append(url))

    gui.main()

    out = capsys.readouterr().out
    assert "Failed to start native window: boom. Falling back to default browser." in out
    assert opened_urls == [f"http://127.0.0.1:{port}"]
