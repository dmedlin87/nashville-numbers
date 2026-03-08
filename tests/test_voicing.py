"""Tests for the voicing module — verifying parity with JS chord voicing."""

import pytest

from nashville_numbers.voicing import (
    extract_chord_root,
    get_bass_midi,
    get_chord_bass_value,
    get_chord_midi_notes,
    get_chord_notes,
    get_chord_root_value,
    get_note_value,
    slot_to_chord_data,
)

# ---------------------------------------------------------------------------
# get_note_value
# ---------------------------------------------------------------------------


class TestGetNoteValue:
    def test_natural_notes(self):
        assert get_note_value("C") == 0
        assert get_note_value("D") == 2
        assert get_note_value("E") == 4
        assert get_note_value("F") == 5
        assert get_note_value("G") == 7
        assert get_note_value("A") == 9
        assert get_note_value("B") == 11

    def test_sharps_and_flats(self):
        assert get_note_value("C#") == 1
        assert get_note_value("Db") == 1
        assert get_note_value("Eb") == 3
        assert get_note_value("F#") == 6
        assert get_note_value("Gb") == 6
        assert get_note_value("Ab") == 8
        assert get_note_value("Bb") == 10

    def test_enharmonic_edge_cases(self):
        assert get_note_value("B#") == 0
        assert get_note_value("Cb") == 11
        assert get_note_value("Fb") == 4
        assert get_note_value("E#") == 5

    def test_strips_quality_suffixes(self):
        assert get_note_value("Am") == 9
        assert get_note_value("Am7") == 9
        assert get_note_value("Cmaj7") == 0
        assert get_note_value("Fdim") == 5
        assert get_note_value("Gaug") == 7
        assert get_note_value("Dsus4") == 2
        assert get_note_value("Dsus2") == 2
        assert get_note_value("Dmin") == 2

    def test_unknown_returns_zero(self):
        assert get_note_value("") == 0
        assert get_note_value("X") == 0


# ---------------------------------------------------------------------------
# extract_chord_root
# ---------------------------------------------------------------------------


class TestExtractChordRoot:
    def test_simple_roots(self):
        assert extract_chord_root("C") == "C"
        assert extract_chord_root("Am") == "A"
        assert extract_chord_root("F#m7") == "F#"
        assert extract_chord_root("Bbmaj7") == "Bb"

    def test_none_for_bad_input(self):
        assert extract_chord_root("") is None
        assert extract_chord_root("1") is None
        assert extract_chord_root(None) is None


# ---------------------------------------------------------------------------
# slot_to_chord_data
# ---------------------------------------------------------------------------


class TestSlotToChordData:
    def test_basic_slot(self):
        slot = {
            "chord": "Am7",
            "key": {"tonic": "C", "mode": "Major"},
        }
        data = slot_to_chord_data(slot)
        assert data["type"] == "chord"
        assert data["text"] == "Am7"
        assert data["root"] == "A"
        assert data["key_tonic"] == "C"
        assert data["key_mode"] == "Major"


# ---------------------------------------------------------------------------
# get_chord_root_value
# ---------------------------------------------------------------------------


class TestGetChordRootValue:
    def test_chord_root(self):
        data = {"type": "chord", "text": "Am", "root": "A"}
        assert get_chord_root_value(data, {"tonic": "C", "mode": "Major"}) == 9

    def test_nns_degree(self):
        # In key of C major, degree 6 = A = 9
        data = {"type": "nns", "text": "6m"}
        assert get_chord_root_value(data, {"tonic": "C", "mode": "Major"}) == 9

    def test_nns_flat_degree(self):
        # In key of C major, b3 = Eb = 3
        data = {"type": "nns", "text": "b3"}
        assert get_chord_root_value(data, {"tonic": "C", "mode": "Major"}) == 3

    def test_nns_sharp_degree(self):
        # In key of C major, #4 = F# = 6
        data = {"type": "nns", "text": "#4"}
        assert get_chord_root_value(data, {"tonic": "C", "mode": "Major"}) == 6

    def test_falls_back_to_text(self):
        data = {"type": "chord", "text": "G"}
        assert get_chord_root_value(data, {"tonic": "C", "mode": "Major"}) == 7


# ---------------------------------------------------------------------------
# get_chord_notes (pitch classes)
# ---------------------------------------------------------------------------


class TestGetChordNotes:
    KEY_C = {"tonic": "C", "mode": "Major"}

    def test_major_triad(self):
        # C = [0, 4, 7]
        data = {"type": "chord", "text": "C", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7]

    def test_minor_triad(self):
        # Am = [9, 0, 4]
        data = {"type": "chord", "text": "Am", "root": "A"}
        assert get_chord_notes(data, self.KEY_C) == [9, 0, 4]

    def test_diminished(self):
        # Bdim = [11, 2, 5]
        data = {"type": "chord", "text": "Bdim", "root": "B"}
        assert get_chord_notes(data, self.KEY_C) == [11, 2, 5]

    def test_augmented(self):
        # Caug = [0, 4, 8]
        data = {"type": "chord", "text": "Caug", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 8]

    def test_sus4(self):
        # Csus4 = [0, 5, 7]
        data = {"type": "chord", "text": "Csus4", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 5, 7]

    def test_sus2(self):
        # Csus2 = [0, 2, 7]
        data = {"type": "chord", "text": "Csus2", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 2, 7]

    def test_dom7(self):
        # G7 = [7, 11, 2, 5]
        data = {"type": "chord", "text": "G7", "root": "G"}
        assert get_chord_notes(data, self.KEY_C) == [7, 11, 2, 5]

    def test_maj7(self):
        # Cmaj7 = [0, 4, 7, 11]
        data = {"type": "chord", "text": "Cmaj7", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 11]

    def test_min7(self):
        # Dm7 = [2, 5, 9, 0]
        data = {"type": "chord", "text": "Dm7", "root": "D"}
        assert get_chord_notes(data, self.KEY_C) == [2, 5, 9, 0]


# ---------------------------------------------------------------------------
# get_chord_midi_notes
# ---------------------------------------------------------------------------


class TestGetChordMidiNotes:
    KEY_C = {"tonic": "C", "mode": "Major"}

    def test_c_major(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        # C3=48, E3=52, G3=55
        assert midis == [48, 52, 55]

    def test_am(self):
        data = {"type": "chord", "text": "Am", "root": "A"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        # A3=57, C4=60, E4=64
        assert midis == [57, 60, 64]

    def test_g7(self):
        data = {"type": "chord", "text": "G7", "root": "G"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        # G3=55, B3=59, D4=62, F4=65
        assert midis == [55, 59, 62, 65]

    def test_max_8_notes(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        assert len(midis) <= 8

    def test_ascending_order(self):
        data = {"type": "chord", "text": "Dm7", "root": "D"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        assert midis == sorted(midis)

    def test_different_key(self):
        # G major: G chord = G3, B3, D4
        data = {"type": "chord", "text": "G", "root": "G"}
        midis = get_chord_midi_notes(data, {"tonic": "G", "mode": "Major"})
        assert midis == [55, 59, 62]


# ---------------------------------------------------------------------------
# get_chord_bass_value / get_bass_midi
# ---------------------------------------------------------------------------


class TestBassVoicing:
    KEY_C = {"tonic": "C", "mode": "Major"}

    def test_bass_value_normal(self):
        data = {"type": "chord", "text": "Am", "root": "A"}
        assert get_chord_bass_value(data, self.KEY_C) == 9  # A

    def test_bass_value_slash_chord(self):
        data = {"type": "chord", "text": "D/F#", "root": "D"}
        assert get_chord_bass_value(data, self.KEY_C) == 6  # F#

    def test_bass_midi_range(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        midi = get_bass_midi(data, self.KEY_C)
        assert 28 <= midi <= 52
        # C2 = 36
        assert midi == 36

    def test_bass_midi_a(self):
        data = {"type": "chord", "text": "Am", "root": "A"}
        midi = get_bass_midi(data, self.KEY_C)
        assert 28 <= midi <= 52
        # 36 + 9 = 45
        assert midi == 45

    def test_bass_midi_clamping_high(self):
        # No note should exceed 52
        for note in ["C", "D", "E", "F", "G", "A", "B"]:
            data = {"type": "chord", "text": note, "root": note}
            midi = get_bass_midi(data, self.KEY_C)
            assert 28 <= midi <= 52

    def test_bass_midi_slash_chord(self):
        data = {"type": "chord", "text": "G/B", "root": "G"}
        midi = get_bass_midi(data, self.KEY_C)
        # B = 11, 36 + 11 = 47
        assert midi == 47
