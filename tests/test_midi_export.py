"""Tests for the MIDI export module."""

import struct
from pathlib import Path

import pytest

from nashville_numbers.midi_export import (
    _vlq,
    _ms_to_ticks,
    _TICKS_PER_BEAT,
    export_midi_bytes,
    export_midi_file,
)
from nashville_numbers.music_lab import build_progression_plan


def _make_plan(input_text="C - Am - F - G", **kwargs):
    defaults = {"tempo": 120, "meter": 4, "groove": "anthem", "count_in_beats": 4, "bass_enabled": True}
    defaults.update(kwargs)
    return build_progression_plan(input_text, **defaults)


# ---------------------------------------------------------------------------
# VLQ encoding
# ---------------------------------------------------------------------------


class TestVlq:
    def test_zero(self):
        assert _vlq(0) == b"\x00"

    def test_small(self):
        assert _vlq(0x7F) == b"\x7F"

    def test_two_bytes(self):
        assert _vlq(0x80) == b"\x81\x00"

    def test_larger(self):
        assert _vlq(0x3FFF) == b"\xFF\x7F"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            _vlq(-1)


# ---------------------------------------------------------------------------
# ms_to_ticks
# ---------------------------------------------------------------------------


class TestMsToTicks:
    def test_one_beat_at_120bpm(self):
        # 500ms = 1 beat at 120 BPM → 480 ticks.
        assert _ms_to_ticks(500, 120) == 480

    def test_zero(self):
        assert _ms_to_ticks(0, 120) == 0

    def test_fractional_rounds(self):
        # 250ms at 120 BPM = 0.5 beat = 240 ticks.
        assert _ms_to_ticks(250, 120) == 240


# ---------------------------------------------------------------------------
# MIDI file structure
# ---------------------------------------------------------------------------


class TestMidiFileStructure:
    def test_starts_with_mthd(self):
        plan = _make_plan()
        data = export_midi_bytes(plan)
        assert data[:4] == b"MThd"

    def test_header_fields(self):
        plan = _make_plan()
        data = export_midi_bytes(plan)
        # MThd header: 4 bytes magic + 4 bytes length + 2 bytes format + 2 bytes tracks + 2 bytes division
        chunk_len, fmt, num_tracks, division = struct.unpack_from(">IhhH", data, 4)
        assert chunk_len == 6
        assert fmt == 1           # Type 1
        assert num_tracks == 2    # tempo track + note track
        assert division == _TICKS_PER_BEAT

    def test_has_two_tracks(self):
        plan = _make_plan()
        data = export_midi_bytes(plan)
        # Count MTrk occurrences.
        count = data.count(b"MTrk")
        assert count == 2

    def test_non_empty_output(self):
        plan = _make_plan()
        data = export_midi_bytes(plan)
        # Header (14) + tempo track + note track: should be well over 50 bytes.
        assert len(data) > 50


# ---------------------------------------------------------------------------
# Note events
# ---------------------------------------------------------------------------


class TestNoteEvents:
    def test_contains_note_on_bytes(self):
        plan = _make_plan()
        data = export_midi_bytes(plan)
        # There should be at least one note-on on channel 0 (0x90).
        assert b"\x90" in data

    def test_no_bass_when_disabled(self):
        from nashville_numbers.sequence import build_arrangement_sequence

        plan = _make_plan(bass_enabled=False)
        seq = build_arrangement_sequence(plan)
        # With bass disabled, no events should be on channel 1.
        ch1 = [e for e in seq["events"] if e.get("channel") == 1]
        assert len(ch1) == 0
        # The MIDI file should still be valid.
        data = export_midi_bytes(plan, sequence=seq)
        assert data[:4] == b"MThd"

    def test_bass_present_when_enabled(self):
        from nashville_numbers.sequence import build_arrangement_sequence

        plan = _make_plan(bass_enabled=True)
        seq = build_arrangement_sequence(plan)
        ch1 = [e for e in seq["events"] if e.get("channel") == 1]
        assert len(ch1) > 0


# ---------------------------------------------------------------------------
# File export
# ---------------------------------------------------------------------------


class TestExportMidiFile:
    def test_writes_file(self, tmp_path):
        plan = _make_plan()
        out = export_midi_file(plan, tmp_path / "test.mid")
        assert out.exists()
        assert out.stat().st_size > 50
        assert out.read_bytes()[:4] == b"MThd"

    def test_returns_path(self, tmp_path):
        plan = _make_plan()
        out = export_midi_file(plan, tmp_path / "out.mid")
        assert isinstance(out, Path)


# ---------------------------------------------------------------------------
# include_count_in flag
# ---------------------------------------------------------------------------


class TestIncludeCountIn:
    def test_smaller_without_count_in(self):
        plan = _make_plan()
        with_ci = export_midi_bytes(plan, include_count_in=True)
        without_ci = export_midi_bytes(plan, include_count_in=False)
        # Without count-in should be smaller (fewer note events).
        assert len(without_ci) < len(with_ci)


# ---------------------------------------------------------------------------
# Pre-built sequence
# ---------------------------------------------------------------------------


class TestPreBuiltSequence:
    def test_accepts_prebuilt_sequence(self):
        from nashville_numbers.sequence import build_arrangement_sequence

        plan = _make_plan()
        seq = build_arrangement_sequence(plan)
        data = export_midi_bytes(plan, sequence=seq)
        assert data[:4] == b"MThd"

    def test_matches_internal_build(self):
        from nashville_numbers.sequence import build_arrangement_sequence

        plan = _make_plan()
        seq = build_arrangement_sequence(plan)
        data_internal = export_midi_bytes(plan)
        data_external = export_midi_bytes(plan, sequence=seq)
        assert data_internal == data_external
