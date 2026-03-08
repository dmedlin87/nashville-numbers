from __future__ import annotations

import pytest

from nashville_numbers.music_lab import build_progression_plan, resolve_groove, GROOVE_PRESETS


def test_build_progression_plan_infers_key_and_assigns_one_bar_per_chord() -> None:
    plan = build_progression_plan("C - Am - F - G", tempo=100, groove="anthem")

    assert plan["input_mode"] == "chords_to_nns"
    assert plan["resolved_key"] == {"tonic": "C", "mode": "Major"}
    assert plan["summary"]["bar_count"] == 4
    assert plan["summary"]["slot_count"] == 4
    assert [bar["preview"] for bar in plan["sections"][0]["bars"]] == ["C", "Am", "F", "G"]
    assert plan["sections"][0]["bars"][1]["slots"][0]["nns"] == "6m"


def test_build_progression_plan_uses_explicit_bars_for_subdivisions() -> None:
    plan = build_progression_plan("| C G | Am F |", meter=4, groove="pulse")

    bars = plan["sections"][0]["bars"]
    assert len(bars) == 2
    assert [slot["beat_duration"] for slot in bars[0]["slots"]] == [2.0, 2.0]
    assert [slot["nns"] for slot in bars[1]["slots"]] == ["6m", "4"]


def test_build_progression_plan_converts_nns_input_when_key_is_present() -> None:
    plan = build_progression_plan("1 - 5 - 6m - 4 in G", groove="pads", bass_enabled=False)

    first_section = plan["sections"][0]
    assert plan["resolved_key"] == {"tonic": "G", "mode": "Major"}
    assert plan["bass_enabled"] is False
    assert [bar["slots"][0]["chord"] for bar in first_section["bars"]] == ["G", "D", "Em", "C"]
    assert first_section["bars"][2]["slots"][0]["nns"] == "6m"


def test_build_progression_plan_requires_key_for_nns_input() -> None:
    with pytest.raises(ValueError, match="Key: REQUIRED"):
        build_progression_plan("1 - 4 - 5")


# ---------------------------------------------------------------------------
# resolve_groove
# ---------------------------------------------------------------------------


class TestResolveGroove:
    def test_resolve_by_id(self):
        g = resolve_groove("anthem")
        assert g["id"] == "anthem"
        assert g["chord_style"] == "strum"

    def test_resolve_case_insensitive(self):
        g = resolve_groove("PULSE")
        assert g["id"] == "pulse"

    def test_unknown_id_raises(self):
        with pytest.raises(ValueError, match="Unknown groove"):
            resolve_groove("nonexistent")

    def test_custom_dict(self):
        custom = {
            "id": "custom",
            "chord_style": "block",
            "strum_ms": 0,
            "gate": 0.5,
            "bass_pattern": "slot-roots",
        }
        g = resolve_groove(custom)
        assert g["id"] == "custom"

    def test_custom_dict_missing_field(self):
        with pytest.raises(ValueError, match="missing required"):
            resolve_groove({"id": "bad"})

    def test_bad_type_raises(self):
        with pytest.raises(TypeError):
            resolve_groove(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Groove preset expansion
# ---------------------------------------------------------------------------


class TestGroovePresetExpansion:
    def test_all_presets_have_explicit_pattern_fields(self):
        for key, preset in GROOVE_PRESETS.items():
            assert "chord_pattern" in preset, f"{key} missing chord_pattern"
            assert "bass_hits" in preset, f"{key} missing bass_hits"
            assert "swing" in preset, f"{key} missing swing"
            assert "humanize_ms" in preset, f"{key} missing humanize_ms"
            assert "velocity_variance" in preset, f"{key} missing velocity_variance"

    def test_expression_values_match_presets(self):
        expected = {
            "anthem": {"swing": 0.0, "humanize_ms": 8, "velocity_variance": 6},
            "pulse": {"swing": 0.0, "humanize_ms": 4, "velocity_variance": 4},
            "lantern": {"swing": 0.3, "humanize_ms": 6, "velocity_variance": 8},
            "pads": {"swing": 0.0, "humanize_ms": 0, "velocity_variance": 0},
            "waltz": {"swing": 0.0, "humanize_ms": 6, "velocity_variance": 5},
            "shuffle": {"swing": 0.5, "humanize_ms": 8, "velocity_variance": 8},
            "funk": {"swing": 0.15, "humanize_ms": 6, "velocity_variance": 10},
            "reggae": {"swing": 0.0, "humanize_ms": 4, "velocity_variance": 6},
            "ballad": {"swing": 0.0, "humanize_ms": 0, "velocity_variance": 0},
        }
        for key, preset in GROOVE_PRESETS.items():
            exp = expected[key]
            assert preset["swing"] == exp["swing"], f"{key} swing mismatch"
            assert preset["humanize_ms"] == exp["humanize_ms"], f"{key} humanize_ms mismatch"
            assert preset["velocity_variance"] == exp["velocity_variance"], f"{key} velocity_variance mismatch"

    def test_plan_includes_expanded_groove(self):
        plan = build_progression_plan("C - F - G", groove="anthem")
        g = plan["groove"]
        assert "bass_hits" in g
        assert "chord_pattern" in g
        assert g["swing"] == 0.0

    def test_all_presets_have_program_fields(self):
        for key, preset in GROOVE_PRESETS.items():
            assert "chord_program" in preset, f"{key} missing chord_program"
            assert "bass_program" in preset, f"{key} missing bass_program"
            assert isinstance(preset["chord_program"], int), f"{key} chord_program not int"
            assert isinstance(preset["bass_program"], int), f"{key} bass_program not int"

    def test_chord_pattern_entries_have_required_fields(self):
        for key, preset in GROOVE_PRESETS.items():
            for i, entry in enumerate(preset["chord_pattern"]):
                assert "beat" in entry, f"{key} chord_pattern[{i}] missing beat"
                assert "velocity_scale" in entry, f"{key} chord_pattern[{i}] missing velocity_scale"


# ---------------------------------------------------------------------------
# New groove presets
# ---------------------------------------------------------------------------


class TestNewGroovePresets:
    def test_waltz_preset(self):
        g = resolve_groove("waltz")
        assert g["id"] == "waltz"
        assert len(g["chord_pattern"]) == 3

    def test_shuffle_preset(self):
        g = resolve_groove("shuffle")
        assert g["id"] == "shuffle"
        assert g["swing"] == 0.5

    def test_funk_preset(self):
        g = resolve_groove("funk")
        assert g["id"] == "funk"
        assert g["gate"] == 0.4

    def test_reggae_has_no_downbeat_chord(self):
        g = resolve_groove("reggae")
        assert g["id"] == "reggae"
        beats = [h["beat"] for h in g["chord_pattern"]]
        assert 0.0 not in beats

    def test_ballad_preset(self):
        g = resolve_groove("ballad")
        assert g["id"] == "ballad"
        assert g["gate"] == 0.95


# ---------------------------------------------------------------------------
# Voice leading plan fields
# ---------------------------------------------------------------------------


class TestVoicingPlanFields:
    def test_plan_includes_voicing_fields(self):
        plan = build_progression_plan("C - F - G", voicing_style="drop2", voice_leading=True)
        assert plan["voicing_style"] == "drop2"
        assert plan["voice_leading"] is True

    def test_plan_voicing_defaults(self):
        plan = build_progression_plan("C - F - G")
        assert plan["voicing_style"] == "close"
        assert plan["voice_leading"] is False


# ---------------------------------------------------------------------------
# Drum pattern presets
# ---------------------------------------------------------------------------


class TestDrumPatternPresets:
    def test_all_presets_have_drum_pattern(self):
        for name, preset in GROOVE_PRESETS.items():
            assert "drum_pattern" in preset, f"Groove '{name}' is missing drum_pattern"

    def test_drum_pattern_entries_have_required_fields(self):
        for name, preset in GROOVE_PRESETS.items():
            for i, hit in enumerate(preset["drum_pattern"]):
                assert "beat" in hit, f"Groove '{name}' drum hit {i} missing 'beat'"
                assert "note" in hit, f"Groove '{name}' drum hit {i} missing 'note'"
                assert "velocity" in hit, f"Groove '{name}' drum hit {i} missing 'velocity'"

    def test_drum_pattern_notes_are_gm_percussion(self):
        for name, preset in GROOVE_PRESETS.items():
            for hit in preset["drum_pattern"]:
                assert 35 <= hit["note"] <= 81, (
                    f"Groove '{name}' has drum note {hit['note']} outside GM range 35-81"
                )

    def test_drum_pattern_velocities_are_valid_midi(self):
        for name, preset in GROOVE_PRESETS.items():
            for hit in preset["drum_pattern"]:
                assert 1 <= hit["velocity"] <= 127, (
                    f"Groove '{name}' has drum velocity {hit['velocity']} outside 1-127"
                )

    def test_pads_and_ballad_have_empty_drum_pattern(self):
        assert GROOVE_PRESETS["pads"]["drum_pattern"] == []
        assert GROOVE_PRESETS["ballad"]["drum_pattern"] == []

    def test_anthem_drum_pattern_has_kick_and_snare(self):
        notes = {hit["note"] for hit in GROOVE_PRESETS["anthem"]["drum_pattern"]}
        assert 36 in notes, "Anthem drum pattern should include kick (36)"
        assert 38 in notes, "Anthem drum pattern should include snare (38)"
