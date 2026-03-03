from nashville_numbers.converter import convert


def test_chords_to_nns_golden_examples() -> None:
    assert convert("C - F - G") == (
        "Key: C Major\n"
        "1 - 4 - 5\n\n"
        "Key: F Major\n"
        "5 - 1 - 2m\n\n"
        "Key: C Minor\n"
        "1m - 4m - 5"
    )

    assert convert("| C | F G | Am |") == (
        "Key: C Major\n"
        "| 1 | 4 5 | 6m |\n\n"
        "Key: F Major\n"
        "| 5 | 1 2m | 3m |\n\n"
        "Key: A Minor\n"
        "| b3 | b6 b7 | 1m |"
    )


def test_nns_to_chords_with_explicit_key() -> None:
    assert convert("1 - 4 - 5 in G") == "Key: G Major\nG - C - D"
    assert convert("Key: Eb Major; 1 6 2 5") == "Key: Eb Major\nEb Cm Fm Bb"


def test_nns_missing_key_requires_key_only() -> None:
    assert convert("1 - 4 - 5") == "Key: REQUIRED"


def test_ambiguous_major_minor_relative_outputs() -> None:
    assert convert("Am - F - C - G") == (
        "Key: C Major\n"
        "6m - 4 - 1 - 5\n\n"
        "Key: F Major\n"
        "3m - 1 - 5 - 2m\n\n"
        "Key: A Minor\n"
        "1m - b6 - b3 - b7"
    )


def test_separator_preservation_and_slash_chord_mapping() -> None:
    assert convert("Cmaj7#11/G, Dm7, G7") == (
        "Key: C Major\n"
        "1(maj7#11)/5, 2m(7), 5(7)\n\n"
        "Key: C Minor\n"
        "1m(maj7#11)/5, 2m(7), 5(7)\n\n"
        "Key: G Minor\n"
        "4m(maj7#11)/1, 5(7), 1m(7)"
    )

    assert convert("C/E - G/B - Am/C") == (
        "Key: G Major\n"
        "4/6 - 1/3 - 2m/4\n\n"
        "Key: C Major\n"
        "1/3 - 5/7 - 6m/1\n\n"
        "Key: A Minor\n"
        "b3/5 - b7/2 - 1m/b3"
    )


def test_conversion_is_deterministic_for_same_input() -> None:
    input_text = "Cmaj7#11/G, Dm7, G7"
    first = convert(input_text)
    for _ in range(20):
        assert convert(input_text) == first


def test_deterministic_for_ambiguous_input() -> None:
    input_text = "Am - F - C - G"
    first = convert(input_text)
    for _ in range(20):
        assert convert(input_text) == first


def test_explicit_key_in_chords_suppresses_candidates() -> None:
    # Pinning the key should yield exactly one block instead of three candidates.
    assert convert("C - F - G in C") == "Key: C Major\n1 - 4 - 5"


def test_minor_chords_to_nns_with_explicit_key() -> None:
    # Harmonic context: E is the (major) dominant V in A minor, so it maps to "5".
    assert convert("Am - G - Dm - E in A minor") == "Key: A Minor\n1m - b7 - 4m - 5"
