from __future__ import annotations

import os
import platform
import sys
import types
from pathlib import Path

import pytest

from nashville_numbers.audio.engine import FluidSynthEngine, _PLATFORM_DRIVER_DEFAULTS, _suppress_stderr
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

    monkeypatch.setattr(
        "nashville_numbers.audio.engine.import_fluidsynth_module",
        lambda: (_ for _ in ()).throw(ImportError("missing")),
    )

    with pytest.raises(AudioUnavailableError) as exc_info:
        FluidSynthEngine(sf2, quality={})
    assert exc_info.value.code == "missing_fluidsynth"


def test_engine_import_tolerates_missing_windows_dll_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if not hasattr(os, "add_dll_directory"):
        pytest.skip("Windows-specific import behavior")

    module_dir = tmp_path / "modules"
    module_dir.mkdir()
    (module_dir / "fluidsynth.py").write_text(
        "import os\n"
        "os.add_dll_directory(r'C:\\tools\\fluidsynth\\bin')\n"
        "class Synth:\n"
        "    pass\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(module_dir))
    monkeypatch.delitem(sys.modules, "fluidsynth", raising=False)

    sf2 = tmp_path / "test.sf2"
    sf2.write_bytes(b"fake")

    try:
        engine = FluidSynthEngine(sf2, quality={})
        assert engine._fluidsynth.Synth is not None
    finally:
        monkeypatch.delitem(sys.modules, "fluidsynth", raising=False)


class TestStartOutputDriverSelection:
    """_start_output should pick a sensible default driver per platform."""

    def _engine_with_fake(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, quality: dict | None = None) -> tuple[FluidSynthEngine, _FakeFluidSynth]:
        fake_module = _FakeFluidSynth()
        monkeypatch.setitem(sys.modules, "fluidsynth", fake_module)
        sf2 = tmp_path / "test.sf2"
        sf2.write_bytes(b"fake")
        engine = FluidSynthEngine(sf2, quality=quality or {})
        return engine, fake_module

    def test_uses_dsound_on_windows(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        engine, fake_module = self._engine_with_fake(monkeypatch, tmp_path)
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        engine.start()
        assert fake_module.instances[0].started_with == "dsound"

    def test_uses_coreaudio_on_darwin(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        engine, fake_module = self._engine_with_fake(monkeypatch, tmp_path)
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        engine.start()
        assert fake_module.instances[0].started_with == "coreaudio"

    def test_uses_pulseaudio_on_linux(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        engine, fake_module = self._engine_with_fake(monkeypatch, tmp_path)
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        engine.start()
        assert fake_module.instances[0].started_with == "pulseaudio"

    def test_configured_driver_overrides_platform_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        engine, fake_module = self._engine_with_fake(monkeypatch, tmp_path, quality={"driver": "alsa"})
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        engine.start()
        assert fake_module.instances[0].started_with == "alsa"

    def test_falls_back_to_autodetect_when_platform_driver_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """If the platform-default driver raises, autodetect (no driver arg) is tried."""

        class _RaisingOnFirstSynth(_FakeSynth):
            def start(self, driver: str | None = None) -> None:
                if driver is not None:
                    raise RuntimeError("driver not available")
                # autodetect call — record None
                self.started_with = None

        fake_module = _FakeFluidSynth()
        fake_module.Synth = lambda: _RaisingOnFirstSynth()  # type: ignore[method-assign]
        monkeypatch.setitem(sys.modules, "fluidsynth", fake_module)
        sf2 = tmp_path / "fallback.sf2"
        sf2.write_bytes(b"fake")
        engine = FluidSynthEngine(sf2, quality={})
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        # Should not raise; falls through to synth.start() with no driver
        engine.start()
        assert engine._synth is not None

    def test_platform_driver_defaults_dict_covers_common_platforms(self) -> None:
        assert "Windows" in _PLATFORM_DRIVER_DEFAULTS
        assert "Darwin" in _PLATFORM_DRIVER_DEFAULTS
        assert "Linux" in _PLATFORM_DRIVER_DEFAULTS


class TestSuppressStderr:
    """_suppress_stderr hides C-library fd-2 output during FluidSynth startup."""

    def test_hides_fd2_writes_made_inside_context(self) -> None:
        """Bytes written to fd 2 inside the context must not reach the original fd."""
        r, w = os.pipe()
        old_2 = os.dup(2)
        os.dup2(w, 2)
        os.close(w)
        try:
            with _suppress_stderr():
                os.write(2, b"HIDDEN\n")
            os.write(2, b"VISIBLE\n")
        finally:
            # Close the write-end of the pipe and restore real stderr.
            write_copy = os.dup(2)
            os.dup2(old_2, 2)
            os.close(old_2)
            os.close(write_copy)

        data = os.read(r, 256)
        os.close(r)
        assert b"HIDDEN" not in data
        assert b"VISIBLE" in data

    def test_restores_fd2_after_exception_in_context(self) -> None:
        """fd 2 must remain usable even when the body raises."""
        with pytest.raises(RuntimeError):
            with _suppress_stderr():
                raise RuntimeError("intentional error")
        # fd 2 is still open; an empty write should not raise.
        os.write(2, b"")

    def test_tolerates_os_error_from_dup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If os.dup raises (e.g., out-of-fd sandbox), the context still yields."""
        monkeypatch.setattr(os, "dup", lambda _fd: (_ for _ in ()).throw(OSError("no fds")))
        reached = False
        with _suppress_stderr():
            reached = True
        assert reached

    def test_start_output_wraps_synth_start_with_suppress(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """_start_output must call _suppress_stderr() around every synth.start() path."""
        import contextlib
        import nashville_numbers.audio.engine as engine_mod

        suppress_calls: list[int] = []

        @contextlib.contextmanager
        def recording_suppress():
            suppress_calls.append(1)
            yield

        monkeypatch.setattr(engine_mod, "_suppress_stderr", recording_suppress)

        fake_module = _FakeFluidSynth()
        monkeypatch.setitem(sys.modules, "fluidsynth", fake_module)
        sf2 = tmp_path / "test.sf2"
        sf2.write_bytes(b"fake")
        engine = FluidSynthEngine(sf2, quality={})
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        engine.start()

        assert len(suppress_calls) >= 1