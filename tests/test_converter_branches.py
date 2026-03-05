from __future__ import annotations

from unittest.mock import patch

import nashville_numbers.converter as converter
from nashville_numbers.converter import _apply_diatonic_defaults, convert


def test_explicit_key_chords_to_nns_uses_single_block() -> None:
    assert convert("C F G in C") == "Key: C Major\n1 4 5"


def test_modulation_uses_section_split_path() -> None:
    progression = (
        "C F G C F G C F G C F G | C F G C F G C F G C F G | "
        "D G A D G A D G A D G A | D G A D G A D G A D G A"
    )
    result = convert(progression)
    assert result.count("Key: ") == 2
    assert "Key: C Major\n" in result
    assert "Key: D Major\n" in result


def test_chords_mode_preserves_non_chord_tokens() -> None:
    assert convert("C xyz G in C") == "Key: C Major\n1 xyz 5"


def test_lowercase_chords_are_preserved_when_chord_regex_does_not_match() -> None:
    assert convert("c f g in C") == "Key: C Major\nc f g"


def test_chord_token_is_preserved_when_note_lookup_is_missing() -> None:
    with patch.dict(converter.NOTE_TO_SEMITONE, {"G": 7}, clear=True):
        assert convert("C in C") == "Key: C Major\nC"


def test_quality_and_extension_edge_cases_are_mapped() -> None:
    assert convert("Cm7b5 Ddim Eaug Fsus2 Gsus Ammaj7 Amin Cmaj9 C(add9) in C") == (
        "Key: C Major\n1m(7b5) 2dim 3aug 4sus2 5sus4 6m(maj7) 6m 1(9) 1(add9)"
    )


def test_empty_parenthesized_extension_falls_back_to_no_extension() -> None:
    assert convert("C() in C") == "Key: C Major\n1"


def test_minor_degree_five_non_minor_quality_normalizes_to_plain_five() -> None:
    assert convert("Eaug in A minor") == "Key: A Minor\n5"


def test_apply_diatonic_defaults_keeps_minor_five_when_lower_starts_with_m() -> None:
    assert _apply_diatonic_defaults("m", "5", "Minor", "m", "m") == "m"


def test_nns_to_chords_preserves_invalid_tokens_and_normalizes_extensions() -> None:
    assert convert("1 xyz 5/7 1maj7 1(9) 1m in C") == (
        "Key: C Major\nC xyz G/B C(maj7) C(9) Cm"
    )
