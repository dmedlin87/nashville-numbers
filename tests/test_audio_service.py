from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

from nashville_numbers.audio.errors import AudioInstallError, AudioUnavailableError
from nashville_numbers.audio.service import AudioService


@dataclass
class ScheduledCall:
    delay_seconds: float
    callback: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[ScheduledCall] = []
        self.clear_calls = 0
        self.stop_calls = 0
        self._next_id = 1

    def schedule(self, delay_seconds: float, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> int:
        event_id = self._next_id
        self._next_id += 1
        self.calls.append(ScheduledCall(float(delay_seconds), callback, args, kwargs))
        return event_id

    def clear(self) -> None:
        self.clear_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def run(self, index: int) -> None:
        scheduled = self.calls[index]
        scheduled.callback(*scheduled.args, **scheduled.kwargs)


class FakeConfigStore:
    def __init__(self, root_dir: Path, config: dict[str, Any] | None = None) -> None:
        self.root_dir = root_dir
        self._config = deepcopy(config or {})
        self.saved_configs: list[dict[str, Any]] = []

    def load(self) -> dict[str, Any]:
        return deepcopy(self._config)

    def save(self, config: dict[str, Any]) -> None:
        snapshot = deepcopy(config)
        self.saved_configs.append(snapshot)
        self._config = snapshot

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = deepcopy(config)


class FakePackInstaller:
    def __init__(
        self,
        status_payload: dict[str, Any] | None = None,
        install_result: Path | None = None,
        install_exc: Exception | None = None,
    ) -> None:
        self._status_payload = deepcopy(
            status_payload
            or {"id": "fluidr3_gm", "installed": False, "path": None}
        )
        self.install_result = install_result
        self.install_exc = install_exc
        self.install_calls = 0

    def status(self) -> dict[str, Any]:
        return deepcopy(self._status_payload)

    def install_default(self) -> Path:
        self.install_calls += 1
        if self.install_exc is not None:
            raise self.install_exc
        assert self.install_result is not None
        self._status_payload.update({"installed": True, "path": str(self.install_result)})
        return self.install_result


class FakeRuntimeInstaller:
    def __init__(
        self,
        status_payload: dict[str, Any] | None = None,
        install_result: dict[str, Any] | None = None,
        install_exc: Exception | None = None,
        install_hook: Callable[[Callable[[int, str], None] | None], None] | None = None,
    ) -> None:
        self._status_payload = deepcopy(
            status_payload or {"runtime_binary": False, "python_binding": False}
        )
        self._install_result = deepcopy(
            install_result
            or {
                "runtime_binary": False,
                "python_binding": False,
                "ready": False,
                "message": "not ready",
            }
        )
        self.install_exc = install_exc
        self.install_hook = install_hook
        self.install_calls = 0
        self.received_callbacks: list[Callable[[int, str], None] | None] = []

    def status(self) -> dict[str, Any]:
        return deepcopy(self._status_payload)

    def install(self, on_progress=None) -> dict[str, Any]:
        self.install_calls += 1
        self.received_callbacks.append(on_progress)
        if self.install_hook is not None:
            self.install_hook(on_progress)
        if self.install_exc is not None:
            raise self.install_exc
        return deepcopy(self._install_result)


class FakeEngine:
    def __init__(
        self,
        soundfont_path: str | Path,
        quality: dict[str, Any] | None = None,
        *,
        start_exc: Exception | None = None,
        note_on_exc: Exception | None = None,
        note_off_exc: Exception | None = None,
    ) -> None:
        self.soundfont_path = str(soundfont_path)
        self.quality = deepcopy(quality)
        self.start_exc = start_exc
        self.note_on_exc = note_on_exc
        self.note_off_exc = note_off_exc
        self.start_calls = 0
        self.note_on_calls: list[tuple[int, int, int]] = []
        self.note_off_calls: list[tuple[int, int]] = []
        self.panic_calls = 0
        self.shutdown_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        if self.start_exc is not None:
            raise self.start_exc

    def note_on(self, channel: int, midi: int, velocity: int) -> None:
        if self.note_on_exc is not None:
            raise self.note_on_exc
        self.note_on_calls.append((channel, midi, velocity))

    def note_off(self, channel: int, midi: int) -> None:
        if self.note_off_exc is not None:
            raise self.note_off_exc
        self.note_off_calls.append((channel, midi))

    def panic(self) -> None:
        self.panic_calls += 1

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class RecordingEngineFactory:
    def __init__(
        self,
        *,
        start_exc: Exception | None = None,
        note_on_exc: Exception | None = None,
        note_off_exc: Exception | None = None,
    ) -> None:
        self.start_exc = start_exc
        self.note_on_exc = note_on_exc
        self.note_off_exc = note_off_exc
        self.instances: list[FakeEngine] = []

    def __call__(self, soundfont_path: str | Path, quality: dict[str, Any] | None) -> FakeEngine:
        engine = FakeEngine(
            soundfont_path,
            quality,
            start_exc=self.start_exc,
            note_on_exc=self.note_on_exc,
            note_off_exc=self.note_off_exc,
        )
        self.instances.append(engine)
        return engine


def _soundfont_file(tmp_path: Path, name: str = "test.sf2") -> Path:
    soundfont = tmp_path / name
    soundfont.write_text("sf2", encoding="utf-8")
    return soundfont


def _build_service(
    *,
    tmp_path: Path,
    config: dict[str, Any] | None = None,
    installer_status: dict[str, Any] | None = None,
    install_result: Path | None = None,
    install_exc: Exception | None = None,
    runtime_status: dict[str, Any] | None = None,
    runtime_result: dict[str, Any] | None = None,
    runtime_exc: Exception | None = None,
    runtime_hook: Callable[[Callable[[int, str], None] | None], None] | None = None,
    engine_start_exc: Exception | None = None,
    engine_note_on_exc: Exception | None = None,
    engine_note_off_exc: Exception | None = None,
) -> tuple[AudioService, FakeConfigStore, FakePackInstaller, FakeRuntimeInstaller, FakeScheduler, RecordingEngineFactory]:
    config_store = FakeConfigStore(tmp_path, config)
    installer = FakePackInstaller(
        status_payload=installer_status,
        install_result=install_result,
        install_exc=install_exc,
    )
    runtime_installer = FakeRuntimeInstaller(
        status_payload=runtime_status,
        install_result=runtime_result,
        install_exc=runtime_exc,
        install_hook=runtime_hook,
    )
    scheduler = FakeScheduler()
    engine_factory = RecordingEngineFactory(
        start_exc=engine_start_exc,
        note_on_exc=engine_note_on_exc,
        note_off_exc=engine_note_off_exc,
    )
    service = AudioService(
        config_store=config_store,
        installer=installer,
        engine_factory=engine_factory,
        scheduler=scheduler,
        runtime_installer=runtime_installer,
    )
    return service, config_store, installer, runtime_installer, scheduler, engine_factory


def test_refresh_uses_configured_soundfont_and_quality(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    config = {
        "enabled": True,
        "soundfont_path": str(soundfont),
        "quality": {"driver": "test", "interpolation_default": 3},
    }

    service, _config_store, installer, _runtime_installer, _scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config=config,
    )

    status = service.status()
    assert status["hq_ready"] is True
    assert status["engine"] == "fluidsynth"
    assert status["reason"] == "ok"
    assert status["pack"] == installer.status()
    assert len(engine_factory.instances) == 1
    engine = engine_factory.instances[0]
    assert engine.soundfont_path == str(soundfont)
    assert engine.quality == config["quality"]
    assert engine.start_calls == 1


def test_refresh_uses_installed_pack_path_when_config_has_no_soundfont(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path, "installed.sf2")
    service, _config_store, installer, _runtime_installer, _scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": None},
        installer_status={"id": "fluidr3_gm", "installed": True, "path": str(soundfont)},
    )

    status = service.status()
    assert status["hq_ready"] is True
    assert status["pack"] == installer.status()
    assert engine_factory.instances[0].soundfont_path == str(soundfont)


def test_refresh_tears_down_existing_engine_when_disabled(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, config_store, _installer, _runtime_installer, _scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
    )
    original_engine = engine_factory.instances[0]

    config_store.set_config({"enabled": False, "soundfont_path": str(soundfont)})
    status = service.refresh()

    assert status["hq_ready"] is False
    assert status["reason"] == "disabled"
    assert original_engine.shutdown_calls == 1
    assert service._engine is None


def test_refresh_reports_audio_unavailable_reason_from_engine(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, _installer, _runtime_installer, _scheduler, _engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
        engine_start_exc=AudioUnavailableError("missing_fluidsynth", "binding missing"),
    )

    status = service.status()
    assert status["hq_ready"] is False
    assert status["engine"] == "unavailable"
    assert status["reason"] == "missing_fluidsynth"


def test_install_default_pack_saves_soundfont_path_and_refreshes(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path, "downloaded.sf2")
    service, config_store, installer, _runtime_installer, _scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": None},
        install_result=soundfont,
    )

    status = service.install_default_pack()

    assert installer.install_calls == 1
    assert config_store.saved_configs[-1]["soundfont_path"] == str(soundfont)
    assert status["hq_ready"] is True
    assert status["pack"]["installed"] is True
    assert status["pack"]["path"] == str(soundfont)
    assert engine_factory.instances[-1].soundfont_path == str(soundfont)


def test_install_default_pack_raises_when_audio_disabled(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, installer, _runtime_installer, _scheduler, _engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": False, "soundfont_path": str(soundfont)},
        install_result=soundfont,
    )

    with pytest.raises(AudioUnavailableError, match="Audio is disabled by configuration"):
        service.install_default_pack()
    assert installer.install_calls == 0


def test_install_default_pack_wraps_unexpected_installer_errors(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, installer, _runtime_installer, _scheduler, _engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
        install_result=soundfont,
        install_exc=RuntimeError("download exploded"),
    )

    with pytest.raises(AudioInstallError) as exc_info:
        service.install_default_pack()

    assert installer.install_calls == 1
    assert exc_info.value.code == "install_failed"
    assert "download exploded" in str(exc_info.value)


def test_install_runtime_forwards_progress_and_refreshes_when_binding_ready(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    progress_events: list[tuple[int, str]] = []

    def record_progress(pct: int, stage: str) -> None:
        progress_events.append((pct, stage))

    def runtime_hook(on_progress: Callable[[int, str], None] | None) -> None:
        assert on_progress is not None
        on_progress(10, "Installing runtime")
        config_store.set_config({"enabled": True, "soundfont_path": str(soundfont)})

    service, config_store, _installer, runtime_installer, _scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": None},
        runtime_result={
            "runtime_binary": True,
            "python_binding": True,
            "ready": True,
            "message": "ready",
        },
        runtime_hook=runtime_hook,
    )

    result = service.install_runtime(on_progress=record_progress)

    assert runtime_installer.install_calls == 1
    assert runtime_installer.received_callbacks == [record_progress]
    assert progress_events == [(10, "Installing runtime"), (92, "Starting audio engine…")]
    assert result["audio_status"]["hq_ready"] is True
    assert engine_factory.instances[-1].soundfont_path == str(soundfont)


def test_install_runtime_returns_current_status_without_refresh_when_binding_missing(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)

    def runtime_hook(_on_progress: Callable[[int, str], None] | None) -> None:
        config_store.set_config({"enabled": True, "soundfont_path": str(soundfont)})

    service, config_store, _installer, runtime_installer, _scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": None},
        runtime_result={
            "runtime_binary": True,
            "python_binding": False,
            "ready": False,
            "message": "binding missing",
        },
        runtime_hook=runtime_hook,
    )

    result = service.install_runtime()

    assert runtime_installer.install_calls == 1
    assert result["audio_status"]["hq_ready"] is False
    assert result["audio_status"]["reason"] == "missing_soundfont"
    assert engine_factory.instances == []


def test_play_note_sends_note_on_and_schedules_note_off(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, _installer, _runtime_installer, scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
    )
    engine = engine_factory.instances[0]

    service.play_note(64, velocity=111, duration_ms=320, channel=2)

    assert engine.note_on_calls == [(2, 64, 111)]
    assert len(scheduler.calls) == 1
    scheduled = scheduler.calls[0]
    assert scheduled.delay_seconds == pytest.approx(0.32)
    assert scheduled.callback.__name__ == "_safe_note_off"
    assert scheduled.args == (2, 64)

    scheduler.run(0)
    assert engine.note_off_calls == [(2, 64)]


def test_play_note_raises_when_service_is_not_ready(tmp_path: Path) -> None:
    service, _config_store, _installer, _runtime_installer, scheduler, _engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": None},
    )

    with pytest.raises(AudioUnavailableError) as exc_info:
        service.play_note(60)

    assert exc_info.value.code == "missing_soundfont"
    assert scheduler.calls == []


def test_play_chord_block_plays_immediately_and_schedules_note_offs(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, _installer, _runtime_installer, scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
    )
    engine = engine_factory.instances[0]

    service.play_chord([60, 64, 67], style="block", note_ms=900, velocity=99, channel=3)

    assert engine.note_on_calls == [(3, 60, 99), (3, 64, 99), (3, 67, 99)]
    assert [call.delay_seconds for call in scheduler.calls] == [pytest.approx(0.9)] * 3
    assert [call.args for call in scheduler.calls] == [(3, 60), (3, 64), (3, 67)]

    scheduler.run(0)
    scheduler.run(1)
    scheduler.run(2)
    assert engine.note_off_calls == [(3, 60), (3, 64), (3, 67)]


def test_play_chord_strum_schedules_note_on_and_note_offs(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, _installer, _runtime_installer, scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
    )
    engine = engine_factory.instances[0]

    service.play_chord([60, 64], style="strum", strum_ms=25, note_ms=700, velocity=88, channel=1)

    assert engine.note_on_calls == []
    assert [call.delay_seconds for call in scheduler.calls] == [
        pytest.approx(0.0),
        pytest.approx(0.7),
        pytest.approx(0.025),
        pytest.approx(0.725),
    ]
    assert [call.callback.__name__ for call in scheduler.calls] == [
        "_safe_note_on",
        "_safe_note_off",
        "_safe_note_on",
        "_safe_note_off",
    ]

    for index in range(len(scheduler.calls)):
        scheduler.run(index)
    assert engine.note_on_calls == [(1, 60, 88), (1, 64, 88)]
    assert engine.note_off_calls == [(1, 60), (1, 64)]


def test_panic_clears_scheduler_and_panics_engine(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, _installer, _runtime_installer, scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
    )
    engine = engine_factory.instances[0]

    service.panic()

    assert scheduler.clear_calls == 1
    assert engine.panic_calls == 1


def test_play_sequence_clears_existing_queue_and_schedules_timed_events(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, _installer, _runtime_installer, scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
    )
    engine = engine_factory.instances[0]

    service.play_sequence(
        [
            {"kind": "note", "delay_ms": 120, "midi": 64, "duration_ms": 250, "velocity": 101, "channel": 2},
            {
                "kind": "chord",
                "delay_ms": 240,
                "midis": [60, 64, 67],
                "duration_ms": 900,
                "velocity": 88,
                "channel": 1,
                "style": "block",
                "strum_ms": 0,
            },
        ]
    )

    assert scheduler.clear_calls == 1
    assert engine.panic_calls == 1
    assert [call.delay_seconds for call in scheduler.calls[:2]] == [
        pytest.approx(0.12),
        pytest.approx(0.24),
    ]

    scheduler.run(0)
    scheduler.run(1)

    assert engine.note_on_calls == [(2, 64, 101), (1, 60, 88), (1, 64, 88), (1, 67, 88)]


def test_shutdown_tears_down_engine_and_stops_scheduler(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, _installer, _runtime_installer, scheduler, engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
    )
    engine = engine_factory.instances[0]

    service.shutdown()

    assert engine.shutdown_calls == 1
    assert scheduler.stop_calls == 1
    assert service._engine is None


def test_runtime_status_returns_runtime_installer_snapshot(tmp_path: Path) -> None:
    service, _config_store, _installer, _runtime_installer, _scheduler, _engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": None},
        runtime_status={"runtime_binary": True, "python_binding": False},
    )

    assert service.runtime_status() == {"runtime_binary": True, "python_binding": False}


def test_scheduled_audio_callbacks_swallow_engine_errors(tmp_path: Path) -> None:
    soundfont = _soundfont_file(tmp_path)
    service, _config_store, _installer, _runtime_installer, scheduler, _engine_factory = _build_service(
        tmp_path=tmp_path,
        config={"enabled": True, "soundfont_path": str(soundfont)},
        engine_note_on_exc=RuntimeError("note-on failed"),
        engine_note_off_exc=RuntimeError("note-off failed"),
    )

    service.play_chord([60], style="strum", strum_ms=25, note_ms=700)

    scheduler.run(0)
    scheduler.run(1)
