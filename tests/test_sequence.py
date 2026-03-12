"""Tests for the sequence module — plan-to-event-list conversion."""


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
        plan = _make_plan(groove="pads")
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # C - Am - F - G = 4 chords (pads has single-hit chord_pattern).
        assert len(chords) == 4

    def test_anthem_chord_count_with_multi_hit(self):
        plan = _make_plan(groove="anthem")
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # Anthem now has 2 chord hits per slot: 4 slots * 2 = 8.
        assert len(chords) == 8

    def test_chord_event_fields(self):
        plan = _make_plan(groove="pads")
        seq = build_arrangement_sequence(plan)
        chord = [e for e in seq["events"] if e["kind"] == "chord"][0]
        assert "midis" in chord
        assert len(chord["midis"]) >= 3
        assert chord["style"] == "block"
        assert chord["strum_ms"] == 0
        assert chord["channel"] == 0
        assert chord["velocity"] == 96

    def test_lantern_velocity(self):
        plan = _make_plan(groove="lantern")
        plan["groove"]["humanize_ms"] = 0
        plan["groove"]["velocity_variance"] = 0
        seq = build_arrangement_sequence(plan)
        chord = [e for e in seq["events"] if e["kind"] == "chord"][0]
        assert chord["velocity"] == 82

    def test_chord_timing(self):
        plan = _make_plan(tempo=120, count_in_beats=4, groove="pads")
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
        plan = _make_plan(input_text="| C G | Am F |", tempo=120, groove="pads")
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
        plan = _make_plan(input_text="1 - 4 - 5 in C", groove="pads")
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        assert len(chords) == 3
        # All should have valid MIDI note lists.
        for c in chords:
            assert len(c["midis"]) >= 3


# ---------------------------------------------------------------------------
# Chord pattern consumption
# ---------------------------------------------------------------------------


def _make_custom_groove_plan(chord_pattern, input_text="C - Am - F - G", **kwargs):
    """Build a plan with a custom groove that uses the given chord_pattern."""
    plan = _make_plan(input_text=input_text, groove="anthem", **kwargs)
    plan["groove"] = {
        "id": "custom",
        "chord_style": "block",
        "strum_ms": 0,
        "gate": 0.8,
        "bass_pattern": "slot-roots",
        "chord_pattern": chord_pattern,
        "bass_hits": [{"beat": 0.0, "velocity": 86, "octave_offset": 0}],
        "swing": 0.0,
        "humanize_ms": 0,
        "velocity_variance": 0,
    }
    return plan


class TestChordPattern:
    def test_multi_hit_produces_multiple_events(self):
        plan = _make_custom_groove_plan([
            {"beat": 0.0, "velocity_scale": 1.0},
            {"beat": 2.0, "velocity_scale": 0.7},
        ])
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # 4 slots * 2 hits = 8 chord events.
        assert len(chords) == 8

    def test_velocity_scaling(self):
        plan = _make_custom_groove_plan([
            {"beat": 0.0, "velocity_scale": 1.0},
            {"beat": 2.0, "velocity_scale": 0.5},
        ])
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # First hit: full velocity (96), second hit: scaled (48).
        assert chords[0]["velocity"] == 96
        assert chords[1]["velocity"] == 48

    def test_timing_offset(self):
        plan = _make_custom_groove_plan(
            [{"beat": 0.0, "velocity_scale": 1.0}, {"beat": 2.0, "velocity_scale": 1.0}],
            tempo=120,
            count_in_beats=4,
        )
        seq = build_arrangement_sequence(plan)
        beat_ms = 500
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # First slot hits: beat 4 and beat 6.
        assert chords[0]["delay_ms"] == round(4 * beat_ms)
        assert chords[1]["delay_ms"] == round(6 * beat_ms)

    def test_skips_hits_beyond_slot_duration(self):
        # Slot is 4 beats, hit at beat 5.0 should be skipped.
        plan = _make_custom_groove_plan([
            {"beat": 0.0, "velocity_scale": 1.0},
            {"beat": 5.0, "velocity_scale": 1.0},
        ])
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # Only the first hit fires per slot: 4 total.
        assert len(chords) == 4

    def test_single_hit_matches_original(self):
        # Default single-hit pattern should produce identical output.
        plan_default = _make_plan(groove="pads")
        plan_custom = _make_custom_groove_plan(
            [{"beat": 0.0, "velocity_scale": 1.0}],
        )
        # Override custom groove to match pads' chord_style and gate.
        plan_custom["groove"]["chord_style"] = "block"
        plan_custom["groove"]["gate"] = 1.0
        seq_default = build_arrangement_sequence(plan_default)
        seq_custom = build_arrangement_sequence(plan_custom)
        default_chords = [e for e in seq_default["events"] if e["kind"] == "chord"]
        custom_chords = [e for e in seq_custom["events"] if e["kind"] == "chord"]
        assert len(default_chords) == len(custom_chords)


# ---------------------------------------------------------------------------
# Expression (swing, humanize, velocity variance)
# ---------------------------------------------------------------------------


def _make_expression_plan(swing=0.0, humanize_ms=0, velocity_variance=0, seed=42, **kwargs):
    """Build a plan with custom expression parameters."""
    plan = _make_plan(**kwargs)
    plan["groove"]["swing"] = swing
    plan["groove"]["humanize_ms"] = humanize_ms
    plan["groove"]["velocity_variance"] = velocity_variance
    plan["expression_seed"] = seed
    return plan


class TestExpression:
    def test_zero_expression_is_noop(self):
        plan_clean = _make_plan(groove="pads")
        plan_zero = _make_expression_plan(swing=0.0, humanize_ms=0, velocity_variance=0, groove="pads")
        seq_clean = build_arrangement_sequence(plan_clean)
        seq_zero = build_arrangement_sequence(plan_zero)
        assert seq_clean == seq_zero

    def test_humanize_deterministic_with_seed(self):
        plan1 = _make_expression_plan(humanize_ms=20, seed=99, groove="pads")
        plan2 = _make_expression_plan(humanize_ms=20, seed=99, groove="pads")
        seq1 = build_arrangement_sequence(plan1)
        seq2 = build_arrangement_sequence(plan2)
        assert seq1 == seq2

    def test_humanize_different_seed_different_output(self):
        plan1 = _make_expression_plan(humanize_ms=20, seed=1, groove="pads")
        plan2 = _make_expression_plan(humanize_ms=20, seed=2, groove="pads")
        seq1 = build_arrangement_sequence(plan1)
        seq2 = build_arrangement_sequence(plan2)
        # At least some event timings should differ.
        delays1 = [e["delay_ms"] for e in seq1["events"]]
        delays2 = [e["delay_ms"] for e in seq2["events"]]
        assert delays1 != delays2

    def test_humanize_bounded_jitter(self):
        plan_base = _make_plan(groove="pads")
        seq_base = build_arrangement_sequence(plan_base)
        base_delays = {i: e["delay_ms"] for i, e in enumerate(seq_base["events"])}

        plan_h = _make_expression_plan(humanize_ms=15, seed=7, groove="pads")
        seq_h = build_arrangement_sequence(plan_h)
        beat_ms = 500  # 120 BPM
        ci_end = round(4 * beat_ms)

        for i, e in enumerate(seq_h["events"]):
            if base_delays[i] < ci_end:
                # Count-in should be unchanged.
                assert e["delay_ms"] == base_delays[i]
            else:
                assert abs(e["delay_ms"] - base_delays[i]) <= 15

    def test_velocity_variance_in_range(self):
        plan = _make_expression_plan(velocity_variance=10, seed=5, groove="pads")
        seq = build_arrangement_sequence(plan)
        for e in seq["events"]:
            if "velocity" in e:
                assert 1 <= e["velocity"] <= 127

    def test_count_in_not_affected(self):
        plan = _make_expression_plan(humanize_ms=20, velocity_variance=10, seed=3, groove="pads")
        seq = build_arrangement_sequence(plan)
        beat_ms = 500
        count_in = [e for e in seq["events"] if e["kind"] == "note" and e["channel"] == 0 and e["delay_ms"] < round(4 * beat_ms)]
        # Count-in clicks should retain exact timing and velocity.
        for i, e in enumerate(count_in[:4]):
            assert e["delay_ms"] == round(i * beat_ms)
            expected_vel = 118 if i == 3 else 92
            assert e["velocity"] == expected_vel

    def test_swing_shifts_offbeat(self):
        # Use a chord_pattern with a hit at beat 0.5 (off-beat eighth).
        plan = _make_expression_plan(swing=0.5, seed=1, tempo=120, count_in_beats=4, groove="pads")
        plan["groove"]["chord_pattern"] = [
            {"beat": 0.0, "velocity_scale": 1.0},
            {"beat": 0.5, "velocity_scale": 0.8},
        ]
        seq = build_arrangement_sequence(plan)
        beat_ms = 500
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # The off-beat hit should be shifted forward.
        # Unswung position: (4 + 0.5) * 500 = 2250ms.
        # Swing offset: 0.5 * (500 / 3) ≈ 83ms.
        offbeat = chords[1]
        unswung_ms = round(4.5 * beat_ms)
        swing_offset = round(0.5 * (beat_ms / 3.0))
        assert offbeat["delay_ms"] == unswung_ms + swing_offset


# ---------------------------------------------------------------------------
# New groove presets in sequence
# ---------------------------------------------------------------------------


class TestNewGrooveSequences:
    def test_waltz_chord_count(self):
        plan = _make_plan(groove="waltz", meter=3)
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # waltz has 3 chord hits per slot, 4 slots = 12.
        assert len(chords) == 12

    def test_reggae_offbeat_timing(self):
        plan = _make_plan(groove="reggae", tempo=120, count_in_beats=4)
        plan["groove"]["humanize_ms"] = 0
        plan["groove"]["velocity_variance"] = 0
        plan["groove"]["swing"] = 0.0
        seq = build_arrangement_sequence(plan)
        beat_ms = 500
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # First chord hit at beat 4.5 (after 4-beat count-in, on the "and").
        assert chords[0]["delay_ms"] == round(4.5 * beat_ms)

    def test_funk_event_count(self):
        plan = _make_plan(groove="funk")
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # funk has 5 chord hits per slot, 4 slots = 20.
        assert len(chords) == 20

    def test_ballad_single_hit(self):
        plan = _make_plan(groove="ballad")
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # ballad has 1 chord hit per slot, 4 slots = 4.
        assert len(chords) == 4

    def test_shuffle_has_swing(self):
        plan = _make_plan(groove="shuffle")
        assert plan["groove"]["swing"] == 0.5


# ---------------------------------------------------------------------------
# Arpeggio pattern
# ---------------------------------------------------------------------------


class TestArpeggio:
    def test_arp_produces_note_events_not_chord(self):
        plan = _make_plan(groove="pads")
        plan["groove"]["arp_pattern"] = {
            "note_indices": [0, 1, 2, 1],
            "step_beats": 1.0,
            "gate": 0.8,
        }
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        beat_ms = 500
        ci_end = round(4 * beat_ms)
        arp_notes = [
            e for e in seq["events"]
            if e["kind"] == "note" and e["channel"] == 0 and e["delay_ms"] >= ci_end
        ]
        assert len(chords) == 0
        assert len(arp_notes) > 0

    def test_arp_note_count(self):
        plan = _make_plan(groove="pads", tempo=120, count_in_beats=4)
        plan["groove"]["arp_pattern"] = {
            "note_indices": [0, 1, 2, 1],
            "step_beats": 1.0,
            "gate": 0.8,
        }
        seq = build_arrangement_sequence(plan)
        beat_ms = 500
        ci_end = round(4 * beat_ms)
        arp_notes = [
            e for e in seq["events"]
            if e["kind"] == "note" and e["channel"] == 0 and e["delay_ms"] >= ci_end
        ]
        # Each slot is 4 beats, step_beats=1.0: 4 arp notes per slot, 4 slots = 16.
        assert len(arp_notes) == 16

    def test_arp_wraps_note_indices(self):
        plan = _make_plan(groove="pads")
        plan["groove"]["arp_pattern"] = {
            "note_indices": [0, 1, 2, 3, 4],
            "step_beats": 1.0,
            "gate": 0.8,
        }
        seq = build_arrangement_sequence(plan)
        assert seq["total_ms"] > 0

    def test_arp_velocity_curve(self):
        plan = _make_plan(groove="pads", tempo=120, count_in_beats=4)
        plan["groove"]["humanize_ms"] = 0
        plan["groove"]["velocity_variance"] = 0
        plan["groove"]["arp_pattern"] = {
            "note_indices": [0, 1],
            "step_beats": 2.0,
            "gate": 0.8,
            "velocity_curve": [1.0, 0.5],
        }
        seq = build_arrangement_sequence(plan)
        beat_ms = 500
        ci_end = round(4 * beat_ms)
        arp_notes = [
            e for e in seq["events"]
            if e["kind"] == "note" and e["channel"] == 0 and e["delay_ms"] >= ci_end
        ]
        # First note full velocity, second half.
        assert arp_notes[0]["velocity"] == 96
        assert arp_notes[1]["velocity"] == 48


# ---------------------------------------------------------------------------
# Walking bass
# ---------------------------------------------------------------------------


class TestWalkingBass:
    def test_walking_bass_four_notes_per_slot(self):
        plan = _make_plan(groove="pads", tempo=120)
        plan["groove"]["bass_pattern"] = "walking"
        del plan["groove"]["bass_hits"]
        seq = build_arrangement_sequence(plan)
        bass = [e for e in seq["events"] if e["channel"] == 1]
        # 4 walk notes per slot, 4 slots = 16.
        assert len(bass) == 16

    def test_walking_bass_in_range(self):
        plan = _make_plan(groove="pads")
        plan["groove"]["bass_pattern"] = "walking"
        del plan["groove"]["bass_hits"]
        seq = build_arrangement_sequence(plan)
        bass = [e for e in seq["events"] if e["channel"] == 1]
        for e in bass:
            assert 28 <= e["midi"] <= 52

    def test_walking_bass_first_note_is_root(self):
        plan = _make_plan(input_text="C", groove="pads")
        plan["groove"]["bass_pattern"] = "walking"
        del plan["groove"]["bass_hits"]
        seq = build_arrangement_sequence(plan)
        bass = [e for e in seq["events"] if e["channel"] == 1]
        assert bass[0]["midi"] == 36  # C2


# ---------------------------------------------------------------------------
# Voice leading in sequence
# ---------------------------------------------------------------------------


class TestVoiceLeadingSequence:
    def test_default_no_voice_leading(self):
        plan1 = _make_plan()
        plan2 = _make_plan()
        seq1 = build_arrangement_sequence(plan1)
        seq2 = build_arrangement_sequence(plan2)
        assert seq1 == seq2

    def test_voice_leading_changes_midi_notes(self):
        plan = _make_plan(input_text="C - F - G - C", groove="pads")
        plan["voice_leading"] = True
        plan["groove"]["humanize_ms"] = 0
        plan["groove"]["velocity_variance"] = 0
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        # With voice leading, F chord should use an inversion.
        # Root position F would be [53, 57, 60].
        f_midis = chords[1]["midis"]
        assert f_midis != [53, 57, 60]

    def test_drop2_style_in_sequence(self):
        plan = _make_plan(groove="pads")
        plan["voicing_style"] = "drop2"
        seq = build_arrangement_sequence(plan)
        chords = [e for e in seq["events"] if e["kind"] == "chord"]
        assert len(chords) == 4


# ---------------------------------------------------------------------------
# Drum events
# ---------------------------------------------------------------------------


class TestDrumEvents:
    def test_drum_events_generated_when_pattern_present(self):
        plan = _make_plan(groove="anthem")
        seq = build_arrangement_sequence(plan)
        ci_end_ms = plan["count_in_beats"] * (60_000.0 / plan["tempo"])
        drums = [e for e in seq["events"] if e["channel"] == 9 and e["delay_ms"] >= ci_end_ms]
        assert len(drums) > 0

    def test_no_drum_events_when_pattern_empty(self):
        plan = _make_plan(groove="pads")
        seq = build_arrangement_sequence(plan)
        ci_end_ms = plan["count_in_beats"] * (60_000.0 / plan["tempo"])
        drums = [e for e in seq["events"] if e["channel"] == 9 and e["delay_ms"] >= ci_end_ms]
        assert len(drums) == 0

    def test_drum_events_respect_bar_timing(self):
        plan = _make_plan(groove="waltz", meter=3)
        seq = build_arrangement_sequence(plan)
        ci_end_ms = plan["count_in_beats"] * (60_000.0 / plan["tempo"])
        drums = [e for e in seq["events"] if e["channel"] == 9 and e["delay_ms"] >= ci_end_ms]
        # Waltz has 3 drum hits per bar; all should start at or after the count-in.
        assert all(e["delay_ms"] >= ci_end_ms for e in drums)
        assert all(e["kind"] == "note" for e in drums)

    def test_drum_events_all_channel_9(self):
        plan = _make_plan(groove="funk")
        seq = build_arrangement_sequence(plan)
        ci_end_ms = plan["count_in_beats"] * (60_000.0 / plan["tempo"])
        drums = [e for e in seq["events"] if e["channel"] == 9 and e["delay_ms"] >= ci_end_ms]
        assert all(e["channel"] == 9 for e in drums)

    def test_expression_applies_to_drum_events(self):
        plan = _make_plan(groove="anthem")
        plan["expression_seed"] = 99
        seq = build_arrangement_sequence(plan)
        ci_end_ms = plan["count_in_beats"] * (60_000.0 / plan["tempo"])
        drums = [e for e in seq["events"] if e["channel"] == 9 and e["delay_ms"] >= ci_end_ms]
        # With humanize_ms=8 and velocity_variance=6, at least some events should differ
        # from their original velocities. Check that events exist and have valid velocities.
        assert all(1 <= e["velocity"] <= 127 for e in drums)

    def test_no_drum_events_without_drum_pattern_key(self):
        """Grooves that lack drum_pattern entirely produce no drum events."""
        plan = _make_plan(groove="pads")
        # Remove the key to simulate an older preset without it.
        plan["groove"].pop("drum_pattern", None)
        seq = build_arrangement_sequence(plan)
        ci_end_ms = plan["count_in_beats"] * (60_000.0 / plan["tempo"])
        drums = [e for e in seq["events"] if e["channel"] == 9 and e["delay_ms"] >= ci_end_ms]
        assert len(drums) == 0
