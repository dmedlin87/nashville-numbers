from __future__ import annotations

import pytest

from nashville_numbers.music_lab import build_progression_plan


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


def test_build_progression_plan_prefix_key_without_semicolon_preserves_progression() -> None:
    plan = build_progression_plan("in C C F G")

    assert plan["resolved_key"] == {"tonic": "C", "mode": "Major"}
    assert [bar["preview"] for bar in plan["sections"][0]["bars"]] == ["C", "F", "G"]
    assert plan["sections"][0]["preview"] == "C | F | G"


def test_build_progression_plan_uses_explicit_key_spelling_for_preview() -> None:
    plan = build_progression_plan("1 4 5 7 in F#")

    assert plan["resolved_key"] == {"tonic": "F#", "mode": "Major"}
    assert [bar["preview"] for bar in plan["sections"][0]["bars"]] == ["F#", "B", "C#", "E#dim"]
    assert plan["sections"][0]["preview"] == "F# | B | C# | E#dim"


def test_build_progression_plan_requires_key_for_nns_input() -> None:
    with pytest.raises(ValueError, match="Key: REQUIRED"):
        build_progression_plan("1 - 4 - 5")
