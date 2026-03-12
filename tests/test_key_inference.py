import pytest
from nashville_numbers.key_inference import (
    KeyChoice,
    infer_keys,
    rank_keys,
    infer_sections,
    _extract_chords,
    _score_key,
    _relative_minor,
    _relative_major,
    _semitone_to_name,
)

def test_semitone_to_name():
    assert _semitone_to_name(0) == "C"
    assert _semitone_to_name(2) == "D"
    assert _semitone_to_name(11) == "B"
    assert _semitone_to_name(-1) == "C"  # fallback behavior

def test_relative_minor():
    assert _relative_minor("C") == "A"
    assert _relative_minor("G") == "E"
    assert _relative_minor("F") == "D"
    assert _relative_minor("Bb") == "G"

def test_relative_major():
    assert _relative_major("A") == "C"
    assert _relative_major("E") == "G"
    assert _relative_major("D") == "F"
    assert _relative_major("G") == "Bb"

def test_extract_chords():
    assert _extract_chords("C - F - G") == [
        (0, "", False, False, False),
        (5, "", False, False, False),
        (7, "", False, False, False),
    ]
    assert _extract_chords("Am Dm E7") == [
        (9, "m", True, False, False),
        (2, "m", True, False, False),
        (4, "7", False, False, True),
    ]
    assert _extract_chords("Cmaj7/G") == [(0, "maj7", False, False, False)]
    assert _extract_chords("not a chord") == []
    assert _extract_chords("1 4 5") == []  # NNS tokens are ignored

def test_score_key():
    chords_c_maj = [
        (0, "", False, False, False),
        (5, "", False, False, False),
        (7, "", False, False, False),
    ]
    score_c_maj = _score_key(chords_c_maj, "C", "Major")
    score_g_maj = _score_key(chords_c_maj, "G", "Major")
    assert score_c_maj > score_g_maj

    chords_a_min = [
        (9, "m", True, False, False),
        (2, "m", True, False, False),
        (4, "7", False, False, True),
    ]
    score_a_min = _score_key(chords_a_min, "A", "Minor")
    score_e_min = _score_key(chords_a_min, "E", "Minor")
    assert score_a_min > score_e_min

def test_rank_keys():
    ranked = rank_keys("C F G")
    assert len(ranked) > 0
    assert ranked[0].choice == KeyChoice("C", "Major")

    ranked_empty = rank_keys("not a chord")
    assert ranked_empty == []

@pytest.mark.parametrize("prog, expected_top", [
    ("C F G", KeyChoice("C", "Major")),
    ("Am Dm E7", KeyChoice("A", "Minor")),
    ("G C D", KeyChoice("G", "Major")),
    ("Dm Gm A7", KeyChoice("D", "Minor")),
    ("invalid", KeyChoice("C", "Major")),
    ("", KeyChoice("C", "Major")),
])
def test_infer_keys(prog, expected_top):
    keys = infer_keys(prog)
    assert keys[0] == expected_top

def test_infer_keys_relative_promotion():
    keys = infer_keys("C Am F G")
    choices = [k for k in keys]
    assert KeyChoice("C", "Major") in choices
    assert KeyChoice("A", "Minor") in choices

def test_infer_sections_single():
    sections = infer_sections("C F G")
    assert len(sections) == 1
    assert sections[0][1] == KeyChoice("C", "Major")

def test_infer_sections_too_few():
    sections = infer_sections("| C | F |")
    assert len(sections) == 1

def test_infer_sections_modulation():
    # We need enough clear parts in the first key and enough in the second key
    # for the margin rule to kick in (margin >= 2.0).
    # `infer_sections` splits on `|`.
    # Let's provide long progressions to boost margins
    prog = "C F G C F G C F G C F G | C F G C F G C F G C F G | D G A D G A D G A D G A | D G A D G A D G A D G A"
    sections = infer_sections(prog)
    assert len(sections) == 2
    assert sections[0][1] == KeyChoice("C", "Major")
    assert sections[1][1] == KeyChoice("D", "Major")

def test_infer_sections_empty():
    sections = infer_sections("|||")
    assert len(sections) == 1
    assert sections[0][1] == KeyChoice("C", "Major")

def test_infer_sections_no_clear_switch():
    # If there's no clear margin/modulation, it stays as one section
    # The margin will be low so it doesn't split
    prog = "| C | F | C | F |"
    sections = infer_sections(prog)
    assert len(sections) == 1
    # Fallback when no clear margin is key for the whole piece
    assert sections[0][1] == KeyChoice("F", "Major")
