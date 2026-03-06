"""FluidSynth engine wrapper."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from .errors import AudioUnavailableError
from .runtime_support import import_fluidsynth_module


class FluidSynthEngine:
    """Small wrapper around pyfluidsynth for note playback."""

    def __init__(self, soundfont_path: str | Path, quality: dict[str, Any] | None = None) -> None:
        self.soundfont_path = Path(soundfont_path)
        self.quality = quality or {}
        self._fluidsynth = self._import_fluidsynth()
        self._synth: Any | None = None
        self._sfid: int | None = None
        self._lock = RLock()

    @staticmethod
    def _import_fluidsynth() -> Any:
        try:
            fluidsynth = import_fluidsynth_module()
        except Exception as exc:
            raise AudioUnavailableError(
                "missing_fluidsynth",
                "FluidSynth is not available. Install extras with: pip install 'nashville-numbers[audio]'",
            ) from exc
        return fluidsynth

    def start(self) -> None:
        if not self.soundfont_path.exists():
            raise AudioUnavailableError(
                "missing_soundfont",
                f"SoundFont not found: {self.soundfont_path}",
            )

        with self._lock:
            if self._synth is not None:
                return

            synth = self._fluidsynth.Synth()
            self._start_output(synth)
            sfid = synth.sfload(str(self.soundfont_path))
            if sfid == -1:
                synth.delete()
                raise AudioUnavailableError("init_error", f"Failed to load SoundFont: {self.soundfont_path}")

            self._configure_effects(synth)
            for channel in range(16):
                synth.program_select(channel, sfid, 0, 0)

            self._synth = synth
            self._sfid = sfid

    def _start_output(self, synth: Any) -> None:
        driver = self.quality.get("driver")
        if driver:
            synth.start(driver=str(driver))
            return

        try:
            synth.start()
        except TypeError:
            synth.start(driver="dsound")

    def _configure_effects(self, synth: Any) -> None:
        reverb = self.quality.get("reverb")
        if isinstance(reverb, dict) and hasattr(synth, "set_reverb"):
            synth.set_reverb(
                float(reverb.get("roomsize", 0.45)),
                float(reverb.get("damping", 0.2)),
                float(reverb.get("width", 0.6)),
                float(reverb.get("level", 0.45)),
            )

        chorus = self.quality.get("chorus")
        if isinstance(chorus, dict) and hasattr(synth, "set_chorus"):
            synth.set_chorus(
                int(chorus.get("nr", 3)),
                float(chorus.get("level", 1.6)),
                float(chorus.get("speed", 0.35)),
                float(chorus.get("depth_ms", 8.0)),
                int(chorus.get("type", 0)),
            )

        if hasattr(synth, "set_interp_method"):
            default_interp = int(self.quality.get("interpolation_default", 4))
            bass_interp = int(self.quality.get("interpolation_bass", 4))
            for channel in range(16):
                method = bass_interp if channel == 1 else default_interp
                try:
                    synth.set_interp_method(channel, method)
                except TypeError:
                    synth.set_interp_method(method)
                    break

    def note_on(self, channel: int, midi: int, velocity: int) -> None:
        with self._lock:
            synth = self._require_started()
            synth.noteon(channel, midi, velocity)

    def note_off(self, channel: int, midi: int) -> None:
        with self._lock:
            synth = self._require_started()
            synth.noteoff(channel, midi)

    def panic(self) -> None:
        with self._lock:
            if self._synth is None:
                return
            for channel in range(16):
                if hasattr(self._synth, "all_notes_off"):
                    self._synth.all_notes_off(channel)
                if hasattr(self._synth, "all_sounds_off"):
                    self._synth.all_sounds_off(channel)

    def shutdown(self) -> None:
        with self._lock:
            if self._synth is None:
                return
            self.panic()
            self._synth.delete()
            self._synth = None
            self._sfid = None

    def _require_started(self) -> Any:
        if self._synth is None:
            raise AudioUnavailableError("init_error", "Audio engine is not initialized")
        return self._synth
