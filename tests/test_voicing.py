"""Tests for the voicing module — verifying parity with JS chord voicing."""


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
# Extended voicings: 6th, 9th, 11th, 13th, add chords, bug fixes
# ---------------------------------------------------------------------------


class TestExtendedVoicings:
    """Extended chord voicings: 6th, 9th, 11th, 13th, add chords, and bug fixes."""

    KEY_C = {"tonic": "C", "mode": "Major"}

    # --- Bug fixes ---

    def test_dim7(self):
        # Bdim7 = B D F Ab = [11, 2, 5, 8] (dim 7th = +9, not +10)
        data = {"type": "chord", "text": "Bdim7", "root": "B"}
        assert get_chord_notes(data, self.KEY_C) == [11, 2, 5, 8]

    def test_mmaj7(self):
        # Cmmaj7 = C Eb G B = [0, 3, 7, 11] (minor 3rd + major 7th)
        data = {"type": "chord", "text": "Cmmaj7", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 3, 7, 11]

    # --- 6th chords ---

    def test_major_6th(self):
        # C6 = C E G A = [0, 4, 7, 9]
        data = {"type": "chord", "text": "C6", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 9]

    def test_minor_6th(self):
        # Cm6 = C Eb G A = [0, 3, 7, 9]
        data = {"type": "chord", "text": "Cm6", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 3, 7, 9]

    # --- 9th chords ---

    def test_dom9(self):
        # C9 = C E G Bb D = [0, 4, 7, 10, 2]
        data = {"type": "chord", "text": "C9", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 10, 2]

    def test_maj9(self):
        # Cmaj9 = C E G B D = [0, 4, 7, 11, 2]
        data = {"type": "chord", "text": "Cmaj9", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 11, 2]

    def test_min9(self):
        # Cm9 = C Eb G Bb D = [0, 3, 7, 10, 2]
        data = {"type": "chord", "text": "Cm9", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 3, 7, 10, 2]

    # --- 11th chords ---

    def test_dom11(self):
        # C11 = C E G Bb D F = [0, 4, 7, 10, 2, 5]
        data = {"type": "chord", "text": "C11", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 10, 2, 5]

    def test_maj11(self):
        # Cmaj11 = C E G B D F = [0, 4, 7, 11, 2, 5]
        data = {"type": "chord", "text": "Cmaj11", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 11, 2, 5]

    def test_min11(self):
        # Cm11 = C Eb G Bb D F = [0, 3, 7, 10, 2, 5]
        data = {"type": "chord", "text": "Cm11", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 3, 7, 10, 2, 5]

    # --- 13th chords ---

    def test_dom13(self):
        # C13 = C E G Bb D A = [0, 4, 7, 10, 2, 9]
        data = {"type": "chord", "text": "C13", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 10, 2, 9]

    def test_maj13(self):
        # Cmaj13 = C E G B D A = [0, 4, 7, 11, 2, 9]
        data = {"type": "chord", "text": "Cmaj13", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 11, 2, 9]

    def test_min13(self):
        # Cm13 = C Eb G Bb D A = [0, 3, 7, 10, 2, 9]
        data = {"type": "chord", "text": "Cm13", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 3, 7, 10, 2, 9]

    # --- add chords ---

    def test_add9(self):
        # Cadd9 = C E G D = [0, 4, 7, 2] (no 7th)
        data = {"type": "chord", "text": "Cadd9", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 2]

    def test_add11(self):
        # Cadd11 = C E G F = [0, 4, 7, 5] (no 7th)
        data = {"type": "chord", "text": "Cadd11", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 5]

    def test_add13(self):
        # Cadd13 = C E G A = [0, 4, 7, 9] (no 7th)
        data = {"type": "chord", "text": "Cadd13", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 9]

    # --- existing types still correct ---

    def test_plain_major_unchanged(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7]

    def test_plain_minor_unchanged(self):
        data = {"type": "chord", "text": "Am", "root": "A"}
        assert get_chord_notes(data, self.KEY_C) == [9, 0, 4]

    def test_dom7_unchanged(self):
        data = {"type": "chord", "text": "G7", "root": "G"}
        assert get_chord_notes(data, self.KEY_C) == [7, 11, 2, 5]

    def test_maj7_unchanged(self):
        data = {"type": "chord", "text": "Cmaj7", "root": "C"}
        assert get_chord_notes(data, self.KEY_C) == [0, 4, 7, 11]


class TestExtendedMidiNotes:
    """MIDI note output for extended chords."""

    KEY_C = {"tonic": "C", "mode": "Major"}

    def test_c9_midi_five_notes_ascending(self):
        data = {"type": "chord", "text": "C9", "root": "C"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        assert midis == sorted(midis)
        assert len(midis) == 5

    def test_c13_midi_six_notes_within_cap(self):
        data = {"type": "chord", "text": "C13", "root": "C"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        assert midis == sorted(midis)
        assert len(midis) == 6
        assert len(midis) <= 8

    def test_dim7_midi_corrected(self):
        data = {"type": "chord", "text": "Bdim7", "root": "B"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        # B3=59, D4=62, F4=65, Ab4=68 (dim7 = +9, not +10)
        assert midis == [59, 62, 65, 68]

    def test_c11_midi_six_notes(self):
        data = {"type": "chord", "text": "C11", "root": "C"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        assert midis == sorted(midis)
        assert len(midis) == 6

    def test_add9_midi_four_notes(self):
        data = {"type": "chord", "text": "Cadd9", "root": "C"}
        midis = get_chord_midi_notes(data, self.KEY_C)
        assert midis == sorted(midis)
        assert len(midis) == 4


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


# ---------------------------------------------------------------------------
# Voicing styles (close, drop-2, drop-3)
# ---------------------------------------------------------------------------


class TestVoicingStyles:
    KEY_C = {"tonic": "C", "mode": "Major"}

    def test_close_default_unchanged(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        assert get_chord_midi_notes(data, self.KEY_C) == [48, 52, 55]

    def test_close_explicit_same_result(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        assert get_chord_midi_notes(data, self.KEY_C, voicing_style="close") == [48, 52, 55]

    def test_drop2_four_note_chord(self):
        data = {"type": "chord", "text": "Cmaj7", "root": "C"}
        # Close: [48, 52, 55, 59]. Drop-2: drop 55→43. Sorted: [43, 48, 52, 59].
        midis = get_chord_midi_notes(data, self.KEY_C, voicing_style="drop2")
        assert midis == [43, 48, 52, 59]

    def test_drop3_four_note_chord(self):
        data = {"type": "chord", "text": "Cmaj7", "root": "C"}
        # Close: [48, 52, 55, 59]. Drop-3: drop 52→40. Sorted: [40, 48, 55, 59].
        midis = get_chord_midi_notes(data, self.KEY_C, voicing_style="drop3")
        assert midis == [40, 48, 55, 59]

    def test_drop2_triad(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        # Triad: [48, 52, 55]. Drop-2: drop 52→40. Sorted: [40, 48, 55].
        midis = get_chord_midi_notes(data, self.KEY_C, voicing_style="drop2")
        assert midis == [40, 48, 55]

    def test_drop3_triad_no_change(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        # Triad only has 3 notes — drop-3 requires >= 4, so no change.
        midis = get_chord_midi_notes(data, self.KEY_C, voicing_style="drop3")
        assert midis == [48, 52, 55]


# ---------------------------------------------------------------------------
# Voice leading
# ---------------------------------------------------------------------------


class TestVoiceLeading:
    KEY_C = {"tonic": "C", "mode": "Major"}

    def test_no_prev_uses_root_position(self):
        data = {"type": "chord", "text": "C", "root": "C"}
        midis = get_chord_midi_notes(data, self.KEY_C, prev_midis=None)
        assert midis == [48, 52, 55]

    def test_c_to_f_minimizes_movement(self):
        c_data = {"type": "chord", "text": "C", "root": "C"}
        f_data = {"type": "chord", "text": "F", "root": "F"}
        c_midis = get_chord_midi_notes(c_data, self.KEY_C)  # [48, 52, 55]
        f_midis = get_chord_midi_notes(f_data, self.KEY_C, prev_midis=c_midis)
        # Voice-led F should have less total movement than root position F [53, 57, 60].
        root_f = [53, 57, 60]
        root_cost = sum(abs(a - b) for a, b in zip(sorted(c_midis), sorted(root_f)))
        led_cost = sum(abs(a - b) for a, b in zip(sorted(c_midis), sorted(f_midis)))
        assert led_cost <= root_cost

    def test_voice_leading_deterministic(self):
        c_data = {"type": "chord", "text": "C", "root": "C"}
        g_data = {"type": "chord", "text": "G", "root": "G"}
        c_midis = get_chord_midi_notes(c_data, self.KEY_C)
        g1 = get_chord_midi_notes(g_data, self.KEY_C, prev_midis=c_midis)
        g2 = get_chord_midi_notes(g_data, self.KEY_C, prev_midis=c_midis)
        assert g1 == g2

    def test_voice_leading_result_ascending(self):
        c_data = {"type": "chord", "text": "C", "root": "C"}
        am_data = {"type": "chord", "text": "Am", "root": "A"}
        c_midis = get_chord_midi_notes(c_data, self.KEY_C)
        am_midis = get_chord_midi_notes(am_data, self.KEY_C, prev_midis=c_midis)
        assert am_midis == sorted(am_midis)

    def test_voice_leading_with_drop2(self):
        c_data = {"type": "chord", "text": "Cmaj7", "root": "C"}
        f_data = {"type": "chord", "text": "Fmaj7", "root": "F"}
        c_midis = get_chord_midi_notes(c_data, self.KEY_C, voicing_style="drop2")
        f_midis = get_chord_midi_notes(
            f_data, self.KEY_C, voicing_style="drop2", prev_midis=c_midis,
        )
        assert f_midis == sorted(f_midis)
        assert len(f_midis) == 4
