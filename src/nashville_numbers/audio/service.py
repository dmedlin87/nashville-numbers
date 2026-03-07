"""Audio service orchestrating config, engine, and scheduler."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .config import AudioConfigStore, InstallStateStore
from .engine import FluidSynthEngine
from .errors import AudioInstallError, AudioUnavailableError
from .installer import DefaultPackInstaller, RuntimeInstaller
from .scheduler import EventScheduler


class AudioService:
    """Facade used by the GUI API handlers."""

    def __init__(
        self,
        config_store: AudioConfigStore | None = None,
        install_state_store: InstallStateStore | None = None,
        installer: DefaultPackInstaller | None = None,
        engine_factory: type[FluidSynthEngine] = FluidSynthEngine,
        scheduler: EventScheduler | None = None,
        runtime_installer: RuntimeInstaller | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._config_store = config_store or AudioConfigStore()
        self._install_state_store = install_state_store or InstallStateStore(self._config_store.root_dir)
        self._installer = installer or DefaultPackInstaller(self._config_store.root_dir)
        self._engine_factory = engine_factory
        self._scheduler = scheduler or EventScheduler()
        self._runtime_installer = runtime_installer or RuntimeInstaller(self._config_store.root_dir)
        self._engine: FluidSynthEngine | None = None
        self._status: dict[str, Any] = {
            "hq_ready": False,
            "hq_requested": True,
            "engine": "unavailable",
            "reason": "init_error",
            "fallback": "web_tone",
            "fallback_active": True,
            "last_install_error": None,
            "pack": self._installer.status(),
        }
        self._config: dict[str, Any] = {}
        self._self_check: dict[str, Any] = {}
        self._max_sequence_events = 512
        self._max_sequence_duration_ms = 180000
        self.refresh()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "hq_ready": bool(self._status["hq_ready"]),
                "hq_requested": bool(self._status.get("hq_requested", True)),
                "engine": str(self._status["engine"]),
                "reason": str(self._status["reason"]),
                "fallback": "web_tone",
                "fallback_active": bool(self._status.get("fallback_active", True)),
                "last_install_error": self._status.get("last_install_error"),
                "config_valid": bool(self._self_check.get("config_valid", True)),
                "self_check": dict(self._self_check),
                "scheduler": self._scheduler.metrics(),
                "install_state": self._install_state_store.load(),
                "pack": dict(self._status.get("pack", {})),
            }

    def refresh(self) -> dict[str, Any]:
        with self._lock:
            self._config = self._config_store.load()
            config_info = self._config_store.load_info()
            self._status["pack"] = self._installer.status()
            self._teardown_engine_locked()
            self._status["hq_requested"] = bool(self._config.get("enabled", True))
            self._status["fallback_active"] = True
            self._self_check = {
                "config_valid": bool(config_info.get("valid", True)),
                "config_reason": config_info.get("reason", "ok"),
                "config_quarantined_to": config_info.get("quarantined_to"),
                "soundfont_path": None,
                "soundfont_readable": False,
                "runtime": self.runtime_status(),
            }

            if not bool(self._config.get("enabled", True)):
                self._status.update({"hq_ready": False, "engine": "unavailable", "reason": "disabled"})
                return self.status()

            soundfont_path = self._resolve_soundfont_path_locked()
            if soundfont_path is None:
                self._status.update({"hq_ready": False, "engine": "unavailable", "reason": "missing_soundfont"})
                return self.status()
            self._self_check["soundfont_path"] = str(soundfont_path)
            self._self_check["soundfont_readable"] = Path(str(soundfont_path)).exists()

            try:
                engine = self._engine_factory(soundfont_path, self._config.get("quality"))
                engine.start()
            except AudioUnavailableError as exc:
                self._status.update({"hq_ready": False, "engine": "unavailable", "reason": exc.code})
            except Exception:
                self._status.update({"hq_ready": False, "engine": "unavailable", "reason": "init_error"})
            else:
                self._engine = engine
                self._status.update(
                    {"hq_ready": True, "engine": "fluidsynth", "reason": "ok", "fallback_active": False}
                )

            return self.status()

    def install_default_pack(self) -> dict[str, Any]:
        with self._lock:
            if not bool(self._config.get("enabled", True)):
                raise AudioUnavailableError("disabled", "Audio is disabled by configuration")

        try:
            soundfont_path = self._installer.install_default()
            self._status["last_install_error"] = None
        except AudioInstallError:
            self._record_install_state(
                {"kind": "default_pack", "running": False, "error": self._status.get("last_install_error")}
            )
            raise
        except Exception as exc:
            raise AudioInstallError("install_failed", f"Failed to install default sound pack: {exc}") from exc

        config = self._config_store.load()
        config["soundfont_path"] = str(soundfont_path)
        self._config_store.save(config)
        self._record_install_state(
            {
                "kind": "default_pack",
                "running": False,
                "result": {
                    "soundfont_path": str(soundfont_path),
                    "pack": self._installer.status(),
                },
            }
        )
        return self.refresh()

    def install_runtime(self, on_progress=None) -> dict[str, Any]:
        """Install FluidSynth runtime binary and pyfluidsynth, then refresh the engine.

        Args:
            on_progress: optional callable(pct: int, stage: str) forwarded to
                         RuntimeInstaller so callers can surface progress updates.
        """
        result = self._runtime_installer.install(on_progress=on_progress)
        self._status["last_install_error"] = result.get("install_error")
        if result.get("python_binding"):
            if on_progress is not None:
                try:
                    on_progress(92, "Starting audio engine…")
                except Exception:
                    pass
            self.refresh()
        return {**result, "audio_status": self.status()}

    def runtime_status(self) -> dict[str, Any]:
        """Return current FluidSynth runtime availability without attempting any install."""
        return dict(self._runtime_installer.status())

    def play_note(self, midi: int, velocity: int = 96, duration_ms: int = 450, channel: int = 0) -> None:
        with self._lock:
            self._require_ready_locked()
            engine = self._engine
            assert engine is not None
            engine.note_on(channel, midi, velocity)
            self._scheduler.schedule(duration_ms / 1000.0, self._safe_note_off, channel, midi)

    def note_on(self, midi: int, velocity: int = 96, channel: int = 0) -> None:
        with self._lock:
            self._require_ready_locked()
            assert self._engine is not None
            self._engine.note_on(channel, midi, velocity)

    def note_off(self, midi: int, channel: int = 0) -> None:
        with self._lock:
            self._require_ready_locked()
            assert self._engine is not None
            self._engine.note_off(channel, midi)

    def play_chord(
        self,
        midis: list[int],
        *,
        style: str = "strum",
        strum_ms: int = 28,
        note_ms: int = 700,
        velocity: int = 96,
        channel: int = 0,
    ) -> None:
        with self._lock:
            self._require_ready_locked()
            assert self._engine is not None

            if style == "block":
                for midi in midis:
                    self._engine.note_on(channel, midi, velocity)
                    self._scheduler.schedule(note_ms / 1000.0, self._safe_note_off, channel, midi)
                return

            for index, midi in enumerate(midis):
                delay = (index * strum_ms) / 1000.0
                self._scheduler.schedule(delay, self._safe_note_on, channel, midi, velocity)
                self._scheduler.schedule(delay + (note_ms / 1000.0), self._safe_note_off, channel, midi)

    def play_sequence(self, events: list[dict[str, Any]], *, reset: bool = True) -> None:
        with self._lock:
            self._require_ready_locked()
            self._validate_sequence(events)
            if reset:
                self._scheduler.clear()
                assert self._engine is not None
                self._engine.panic()

            for event in events:
                delay_seconds = max(0.0, float(event.get("delay_ms", 0))) / 1000.0
                kind = str(event.get("kind", "")).lower()

                if kind == "note":
                    self._scheduler.schedule(
                        delay_seconds,
                        self._play_note_event,
                        int(event["midi"]),
                        int(event.get("velocity", 96)),
                        int(event.get("duration_ms", 450)),
                        int(event.get("channel", 0)),
                    )
                    continue

                if kind == "chord":
                    self._scheduler.schedule(
                        delay_seconds,
                        self._play_chord_event,
                        list(event["midis"]),
                        str(event.get("style", "strum")),
                        int(event.get("strum_ms", 28)),
                        int(event.get("duration_ms", event.get("note_ms", 700))),
                        int(event.get("velocity", 96)),
                        int(event.get("channel", 0)),
                    )

    def panic(self) -> None:
        with self._lock:
            self._scheduler.clear()
            if self._engine is not None:
                self._engine.panic()

    def shutdown(self) -> None:
        with self._lock:
            self._teardown_engine_locked()
        self._scheduler.stop()

    def _safe_note_on(self, channel: int, midi: int, velocity: int) -> None:
        with self._lock:
            if self._engine is None:
                return
            try:
                self._engine.note_on(channel, midi, velocity)
            except Exception as exc:
                self._record_callback_error("note_on", exc)
                return

    def _safe_note_off(self, channel: int, midi: int) -> None:
        with self._lock:
            if self._engine is None:
                return
            try:
                self._engine.note_off(channel, midi)
            except Exception as exc:
                self._record_callback_error("note_off", exc)
                return

    def _play_note_event(self, midi: int, velocity: int, duration_ms: int, channel: int) -> None:
        self.play_note(midi, velocity=velocity, duration_ms=duration_ms, channel=channel)

    def _play_chord_event(
        self,
        midis: list[int],
        style: str,
        strum_ms: int,
        note_ms: int,
        velocity: int,
        channel: int,
    ) -> None:
        self.play_chord(
            midis,
            style=style,
            strum_ms=strum_ms,
            note_ms=note_ms,
            velocity=velocity,
            channel=channel,
        )

    def _teardown_engine_locked(self) -> None:
        if self._engine is not None:
            self._engine.shutdown()
            self._engine = None

    def _resolve_soundfont_path_locked(self) -> str | Path | None:
        configured = self._config.get("soundfont_path")
        if configured:
            configured_path = Path(str(configured))
            if configured_path.exists():
                return str(configured_path)
            self._self_check["soundfont_path"] = str(configured_path)
            self._self_check["soundfont_readable"] = False

        pack_status = self._status.get("pack", {})
        pack_path = pack_status.get("path") if isinstance(pack_status, dict) else None
        if pack_path and Path(str(pack_path)).exists():
            return str(pack_path)
        return None

    def _require_ready_locked(self) -> None:
        if self._engine is None or not bool(self._status.get("hq_ready")):
            reason = str(self._status.get("reason", "init_error"))
            raise AudioUnavailableError(reason, "High-quality audio engine is unavailable")

    @property
    def root_dir(self) -> Path:
        return self._config_store.root_dir

    def _record_install_state(self, payload: dict[str, Any]) -> None:
        try:
            self._install_state_store.save(payload)
        except OSError:
            return

    def _record_callback_error(self, stage: str, exc: Exception) -> None:
        self._status["last_install_error"] = f"{stage}: {exc}"

    def _validate_sequence(self, events: list[dict[str, Any]]) -> None:
        if len(events) > self._max_sequence_events:
            raise AudioUnavailableError("overloaded", "Audio sequence exceeds queue limits")
        if self._scheduler.queue_depth() > self._max_sequence_events:
            raise AudioUnavailableError("overloaded", "Audio scheduler is overloaded")
        total_notes = 0
        max_end = 0
        for event in events:
            kind = str(event.get("kind", "")).lower()
            delay_ms = max(0, int(event.get("delay_ms", 0)))
            duration_ms = max(0, int(event.get("duration_ms", event.get("note_ms", 0))))
            max_end = max(max_end, delay_ms + duration_ms)
            if kind == "note":
                total_notes += 1
            elif kind == "chord":
                total_notes += len(list(event.get("midis", [])))
        if max_end > self._max_sequence_duration_ms or total_notes > self._max_sequence_events:
            raise AudioUnavailableError("overloaded", "Audio sequence exceeds scheduler limits")


_AUDIO_SERVICE: AudioService | None = None
_AUDIO_LOCK = threading.Lock()


def get_audio_service() -> AudioService:
    global _AUDIO_SERVICE
    with _AUDIO_LOCK:
        if _AUDIO_SERVICE is None:
            _AUDIO_SERVICE = AudioService()
        return _AUDIO_SERVICE

