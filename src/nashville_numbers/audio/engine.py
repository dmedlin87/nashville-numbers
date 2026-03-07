"""FluidSynth engine wrapper."""

from __future__ import annotations

import contextlib
import os
import platform
from pathlib import Path
from threading import RLock
from typing import Any

from .errors import AudioUnavailableError
from .runtime_support import import_fluidsynth_module

# Preferred audio driver per platform.  Defaulting here avoids FluidSynth
# probing every available backend on start-up, which prints SDL3/MIDI/device
# warnings to stderr even when audio ultimately works.
_PLATFORM_DRIVER_DEFAULTS: dict[str, str] = {
    "Windows": "dsound",
    "Darwin": "coreaudio",
    "Linux": "pulseaudio",
}


@contextlib.contextmanager
def _suppress_stderr():
    """Redirect C-library stderr (fd 2) to /dev/null for the duration.

    pyfluidsynth's start() unconditionally creates a MIDI input driver even
    when no MIDI device is present, which prints "not enough MIDI in devices"
    and SDL3 probing warnings to the C-level stderr.  Suppressing fd 2 during
    the start() call hides these cosmetic messages while leaving the Python
    logging stream intact after the call returns.
    """
    try:
        devnull_fd = os.open(os.devnull, os.O_RDWR)
        saved_fd = os.dup(2)
    except OSError:
        yield
        return
    try:
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)
        os.close(devnull_fd)


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
        driver = self.quality.get("driver") or _PLATFORM_DRIVER_DEFAULTS.get(platform.system())
        if driver:
            try:
                with _suppress_stderr():
                    synth.start(driver=str(driver))
                return
            except Exception:
                pass  # fall through to unguided start

        try:
            with _suppress_stderr():
                synth.start()
        except TypeError:
            with _suppress_stderr():
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
