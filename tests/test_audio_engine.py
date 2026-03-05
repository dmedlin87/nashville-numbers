from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path

import pytest

from nashville_numbers.audio.engine import FluidSynthEngine
from nashville_numbers.audio.errors import AudioUnavailableError


class _FakeSynth:
    def __init__(self) -> None:
        self.started_with: str | None = None
        self.sfload_path: str | None = None
        self.program_select_calls: list[tuple[int, int, int, int]] = []
        self.note_on_calls: list[tuple[int, int, int]] = []
        self.note_off_calls: list[tuple[int, int]] = []
        self.reverb_calls: list[tuple[float, float, float, float]] = []
        self.chorus_calls: list[tuple[int, float, float, float, int]] = []
        self.interp_calls: list[tuple[int, int]] = []
        self.all_notes_off_calls: list[int] = []
        self.all_sounds_off_calls: list[int] = []
        self.delete_calls = 0

    def start(self, driver: str | None = None) -> None:
        self.started_with = driver or "default"

    def sfload(self, path: str) -> int:
        self.sfload_path = path
        return 7

    def program_select(self, channel: int, sfid: int, bank: int, preset: int) -> None:
        self.program_select_calls.append((channel, sfid, bank, preset))

    def noteon(self, channel: int, midi: int, velocity: int) -> None:
        self.note_on_calls.append((channel, midi, velocity))

    def noteoff(self, channel: int, midi: int) -> None:
        self.note_off_calls.append((channel, midi))

    def set_reverb(self, roomsize: float, damping: float, width: float, level: float) -> None:
        self.reverb_calls.append((roomsize, damping, width, level))

    def set_chorus(self, nr: int, level: float, speed: float, depth_ms: float, kind: int) -> None:
        self.chorus_calls.append((nr, level, speed, depth_ms, kind))

    def set_interp_method(self, channel: int, method: int) -> None:
        self.interp_calls.append((channel, method))

    def all_notes_off(self, channel: int) -> None:
        self.all_notes_off_calls.append(channel)

    def all_sounds_off(self, channel: int) -> None:
        self.all_sounds_off_calls.append(channel)

    def delete(self) -> None:
        self.delete_calls += 1


class _FakeFluidSynth(types.SimpleNamespace):
    def __init__(self) -> None:
        super().__init__()
        self.instances: list[_FakeSynth] = []

    def Synth(self) -> _FakeSynth:  # noqa: N802 - mirrors library API
        synth = _FakeSynth()
        self.instances.append(synth)
        return synth


def test_engine_start_and_note_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_module = _FakeFluidSynth()
    monkeypatch.setitem(sys.modules, "fluidsynth", fake_module)

    sf2 = tmp_path / "FluidR3_GM.sf2"
    sf2.write_bytes(b"fake")

    engine = FluidSynthEngine(
        sf2,
        quality={
            "interpolation_default": 4,
            "interpolation_bass": 4,
            "reverb": {"roomsize": 0.5, "damping": 0.2, "width": 0.6, "level": 0.4},
            "chorus": {"nr": 3, "level": 1.6, "speed": 0.35, "depth_ms": 8.0, "type": 0},
        },
    )
    engine.start()
    engine.note_on(0, 60, 100)
    engine.note_off(0, 60)

    synth = fake_module.instances[0]
    assert synth.sfload_path == str(sf2)
    assert len(synth.program_select_calls) == 16
    assert synth.note_on_calls == [(0, 60, 100)]
    assert synth.note_off_calls == [(0, 60)]
    assert synth.reverb_calls
    assert synth.chorus_calls
    assert len(synth.interp_calls) == 16


def test_engine_panic_and_shutdown_are_safe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_module = _FakeFluidSynth()
    monkeypatch.setitem(sys.modules, "fluidsynth", fake_module)
    sf2 = tmp_path / "test.sf2"
    sf2.write_bytes(b"fake")

    engine = FluidSynthEngine(sf2, quality={})
    engine.start()
    engine.panic()
    engine.shutdown()
    engine.shutdown()

    synth = fake_module.instances[0]
    assert len(synth.all_notes_off_calls) == 32  # panic + shutdown panic
    assert len(synth.all_sounds_off_calls) == 32
    assert synth.delete_calls == 1


def test_engine_raises_when_soundfont_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_module = _FakeFluidSynth()
    monkeypatch.setitem(sys.modules, "fluidsynth", fake_module)
    missing = tmp_path / "missing.sf2"

    engine = FluidSynthEngine(missing, quality={})
    with pytest.raises(AudioUnavailableError, match="SoundFont not found") as exc_info:
        engine.start()
    assert exc_info.value.code == "missing_soundfont"


def test_engine_raises_when_fluidsynth_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sf2 = tmp_path / "test.sf2"
    sf2.write_bytes(b"fake")

    real_import = builtins.__import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[no-untyped-def]
        if name == "fluidsynth":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "fluidsynth", raising=False)

    with pytest.raises(AudioUnavailableError) as exc_info:
        FluidSynthEngine(sf2, quality={})
    assert exc_info.value.code == "missing_fluidsynth"

