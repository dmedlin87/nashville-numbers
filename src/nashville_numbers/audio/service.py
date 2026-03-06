"""Audio service orchestrating config, engine, and scheduler."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .config import AudioConfigStore
from .engine import FluidSynthEngine
from .errors import AudioInstallError, AudioUnavailableError
from .installer import DefaultPackInstaller, RuntimeInstaller
from .scheduler import EventScheduler


class AudioService:
    """Facade used by the GUI API handlers."""

    def __init__(
        self,
        config_store: AudioConfigStore | None = None,
        installer: DefaultPackInstaller | None = None,
        engine_factory: type[FluidSynthEngine] = FluidSynthEngine,
        scheduler: EventScheduler | None = None,
        runtime_installer: RuntimeInstaller | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._config_store = config_store or AudioConfigStore()
        self._installer = installer or DefaultPackInstaller(self._config_store.root_dir)
        self._engine_factory = engine_factory
        self._scheduler = scheduler or EventScheduler()
        self._runtime_installer = runtime_installer or RuntimeInstaller(self._config_store.root_dir)
        self._engine: FluidSynthEngine | None = None
        self._status: dict[str, Any] = {
            "hq_ready": False,
            "engine": "unavailable",
            "reason": "init_error",
            "fallback": "web_tone",
            "pack": self._installer.status(),
        }
        self._config: dict[str, Any] = {}
        self.refresh()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "hq_ready": bool(self._status["hq_ready"]),
                "engine": str(self._status["engine"]),
                "reason": str(self._status["reason"]),
                "fallback": "web_tone",
                "pack": dict(self._status.get("pack", {})),
            }

    def refresh(self) -> dict[str, Any]:
        with self._lock:
            self._config = self._config_store.load()
            self._status["pack"] = self._installer.status()
            self._teardown_engine_locked()

            if not bool(self._config.get("enabled", True)):
                self._status.update({"hq_ready": False, "engine": "unavailable", "reason": "disabled"})
                return self.status()

            soundfont_path = self._resolve_soundfont_path_locked()
            if soundfont_path is None:
                self._status.update({"hq_ready": False, "engine": "unavailable", "reason": "missing_soundfont"})
                return self.status()

            try:
                engine = self._engine_factory(soundfont_path, self._config.get("quality"))
                engine.start()
            except AudioUnavailableError as exc:
                self._status.update({"hq_ready": False, "engine": "unavailable", "reason": exc.code})
            except Exception:
                self._status.update({"hq_ready": False, "engine": "unavailable", "reason": "init_error"})
            else:
                self._engine = engine
                self._status.update({"hq_ready": True, "engine": "fluidsynth", "reason": "ok"})

            return self.status()

    def install_default_pack(self) -> dict[str, Any]:
        with self._lock:
            if not bool(self._config.get("enabled", True)):
                raise AudioUnavailableError("disabled", "Audio is disabled by configuration")

        try:
            soundfont_path = self._installer.install_default()
        except AudioInstallError:
            raise
        except Exception as exc:
            raise AudioInstallError("install_failed", f"Failed to install default sound pack: {exc}") from exc

        config = self._config_store.load()
        config["soundfont_path"] = str(soundfont_path)
        self._config_store.save(config)
        return self.refresh()

    def install_runtime(self, on_progress=None) -> dict[str, Any]:
        """Install FluidSynth runtime binary and pyfluidsynth, then refresh the engine.

        Args:
            on_progress: optional callable(pct: int, stage: str) forwarded to
                         RuntimeInstaller so callers can surface progress updates.
        """
        result = self._runtime_installer.install(on_progress=on_progress)
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
            except Exception:
                return

    def _safe_note_off(self, channel: int, midi: int) -> None:
        with self._lock:
            if self._engine is None:
                return
            try:
                self._engine.note_off(channel, midi)
            except Exception:
                return

    def _teardown_engine_locked(self) -> None:
        if self._engine is not None:
            self._engine.shutdown()
            self._engine = None

    def _resolve_soundfont_path_locked(self) -> str | Path | None:
        configured = self._config.get("soundfont_path")
        if configured and Path(str(configured)).exists():
            return str(configured)

        pack_status = self._status.get("pack", {})
        pack_path = pack_status.get("path") if isinstance(pack_status, dict) else None
        if pack_path and Path(str(pack_path)).exists():
            return str(pack_path)
        return None

    def _require_ready_locked(self) -> None:
        if self._engine is None or not bool(self._status.get("hq_ready")):
            reason = str(self._status.get("reason", "init_error"))
            raise AudioUnavailableError(reason, "High-quality audio engine is unavailable")


_AUDIO_SERVICE: AudioService | None = None
_AUDIO_LOCK = threading.Lock()


def get_audio_service() -> AudioService:
    global _AUDIO_SERVICE
    with _AUDIO_LOCK:
        if _AUDIO_SERVICE is None:
            _AUDIO_SERVICE = AudioService()
        return _AUDIO_SERVICE

