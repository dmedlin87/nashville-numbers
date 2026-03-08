"""Tests for the sequence module — plan-to-event-list conversion."""

import pytest

from nashville_numbers.music_lab import build_progression_plan
from nashville_numbers.sequence import build_arrangement_sequence


def _make_plan(input_text="C - Am - F - G", **kwargs):
    defaults = {"tempo": 120, "meter": 4, "groove": "anthem", "count_in_beats": 4, "bass_enabled": True}
    defaults.update(kwargs)
    return build_progression_plan(input_text, **defaults)


# ---------------------------------------------------------------------------
# Count-in events
# ---------------------------------------------------------------------------


class TestCountIn:
    def test_count_in_events(self):
        plan = _make_plan()
        seq = build_arrangement_sequence(plan)
        # First 4 events should be count-in clicks (note events on channel 0).
        count_in = [e for e in seq["events"] if e["kind"] == "note" and e["channel"] == 0]
        assert len(count_in) >= 4
        first_four = count_in[:4]
        # All are note events.
        assert all(e["kind"] == "note" for e in first_four)
        # Last click is accented (velocity 118, midi 84).
        assert first_four[3]["velocity"] == 118
        assert first_four[3]["midi"] == 84
        # Others are regular (velocity 92, midi 79).
        for e in first_four[:3]:
            assert e["velocity"] == 92
            assert e["midi"] == 79

    def test_count_in_timing(self):
        plan = _make_plan(tempo=120)
        seq = build_arrangement_sequence(plan)
        beat_ms = 60_000 / 120  # 500ms
        count_in = [e for e in seq["events"] if e["kind"] == "note" and e["channel"] == 0][:4]
        for i, e in enumerate(count_in):
            assert e["delay_ms"] == round(i * beat_ms)


# ---------------------------------------------------------------------------
# Chord events
# ---------------------------------------------------------------------------


class TestChordEvents:
    def test_chord_event_count(self):
        plan = _make_plan()
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # C - Am - F - G = 4 chords.
        assert len(chords) == 4

    def test_chord_event_fields(self):
        plan = _make_plan(groove="anthem")
        seq = build_arrangement_sequence(plan)
        chord = [e for e in seq["events"] if e["kind"] == "chord"][0]
        assert "midis" in chord
        assert len(chord["midis"]) >= 3
        assert chord["style"] == "strum"
        assert chord["strum_ms"] == 24
        assert chord["channel"] == 0
        assert chord["velocity"] == 96

    def test_lantern_velocity(self):
        plan = _make_plan(groove="lantern")
        seq = build_arrangement_sequence(plan)
        chord = [e for e in seq["events"] if e["kind"] == "chord"][0]
        assert chord["velocity"] == 82

    def test_chord_timing(self):
        plan = _make_plan(tempo=120, count_in_beats=4)
        seq = build_arrangement_sequence(plan)
        beat_ms = 500  # 60000 / 120
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # Chords start after count-in (4 beats = 2000ms).
        assert chords[0]["delay_ms"] == round(4 * beat_ms)
        # Each chord is 4 beats apart (one per bar in 4/4).
        for i in range(1, len(chords)):
            expected = round((4 + i * 4) * beat_ms)
            assert chords[i]["delay_ms"] == expected


# ---------------------------------------------------------------------------
# Bass events
# ---------------------------------------------------------------------------


class TestBassEvents:
    def test_bass_present_when_enabled(self):
        plan = _make_plan(bass_enabled=True)
        seq = build_arrangement_sequence(plan)
        bass = [e for e in seq["events"] if e["channel"] == 1]
        assert len(bass) > 0

    def test_no_bass_when_disabled(self):
        plan = _make_plan(bass_enabled=False)
        seq = build_arrangement_sequence(plan)
        bass = [e for e in seq["events"] if e["channel"] == 1]
        assert len(bass) == 0

    def test_anthem_bass_pattern(self):
        # Anthem = downbeat-octave: root on every bar + octave if beat_duration >= 2.
        plan = _make_plan(groove="anthem")
        seq = build_arrangement_sequence(plan)
        bass = [e for e in seq["events"] if e["channel"] == 1]
        # Each chord has 4 beats, so downbeat-octave gives 2 bass events per chord.
        assert len(bass) == 8  # 4 chords * 2 bass events

    def test_pulse_bass_pattern(self):
        # Pulse = slot-roots: one bass note per slot.
        plan = _make_plan(groove="pulse")
        seq = build_arrangement_sequence(plan)
        bass = [e for e in seq["events"] if e["channel"] == 1]
        assert len(bass) == 4  # one per chord slot

    def test_pads_bass_pattern(self):
        # Pads = bar-root: bass only on beat_start == 0.
        plan = _make_plan(groove="pads")
        seq = build_arrangement_sequence(plan)
        bass = [e for e in seq["events"] if e["channel"] == 1]
        # One chord per bar, each starts at beat 0 → one bass per bar.
        assert len(bass) == 4


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------


class TestHighlights:
    def test_highlight_per_slot(self):
        plan = _make_plan()
        seq = build_arrangement_sequence(plan)
        assert len(seq["highlights"]) == 4
        for h in seq["highlights"]:
            assert "key" in h
            assert "delay_ms" in h
            assert "duration_ms" in h


# ---------------------------------------------------------------------------
# Total duration
# ---------------------------------------------------------------------------


class TestTotalMs:
    def test_total_ms_consistency(self):
        plan = _make_plan(tempo=120, count_in_beats=4)
        seq = build_arrangement_sequence(plan)
        beat_ms = 500
        expected_beats = 4 + 16  # count-in + 4 bars * 4 beats
        expected_ms = round(expected_beats * beat_ms + 240)
        assert seq["total_ms"] == expected_ms


# ---------------------------------------------------------------------------
# Multi-slot bars
# ---------------------------------------------------------------------------


class TestMultiSlotBars:
    def test_subdivided_bar(self):
        plan = _make_plan(input_text="| C G | Am F |", tempo=120)
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # 2 bars with 2 chords each = 4 chord events.
        assert len(chords) == 4

    def test_subdivided_bar_timing(self):
        plan = _make_plan(input_text="| C G | Am F |", tempo=120)
        seq = build_arrangement_sequence(plan)
        beat_ms = 500
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # Bar 1: C at beat 4, G at beat 6 (each slot is 2 beats in 4/4).
        assert chords[0]["delay_ms"] == round(4 * beat_ms)
        assert chords[1]["delay_ms"] == round(6 * beat_ms)
        # Bar 2: Am at beat 8, F at beat 10.
        assert chords[2]["delay_ms"] == round(8 * beat_ms)
        assert chords[3]["delay_ms"] == round(10 * beat_ms)


# ---------------------------------------------------------------------------
# NNS input
# ---------------------------------------------------------------------------


class TestNnsInput:
    def test_nns_with_key(self):
        plan = _make_plan(input_text="1 - 4 - 5 in C")
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        assert len(chords) == 3
        # All should have valid MIDI note lists.
        for c in chords:
            assert len(c["midis"]) >= 3
