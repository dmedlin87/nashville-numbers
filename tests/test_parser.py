from nashville_numbers.parser import tokenize_progression, parse_input, ProgressionToken

def test_tokenize_progression_nns():
    tokens = tokenize_progression("1 b3 1m 1/3 5(7)")
    assert tokens == [
        ProgressionToken("1", "nns"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("b3", "nns"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("1m", "nns"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("1/3", "nns"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("5(7)", "nns"),
    ]

def test_tokenize_progression_chords():
    tokens = tokenize_progression("C Am Bb/D Gmaj7")
    assert tokens == [
        ProgressionToken("C", "chord"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("Am", "chord"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("Bb/D", "chord"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("Gmaj7", "chord"),
    ]

def test_tokenize_progression_separators():
    tokens = tokenize_progression("C,Am - Bb | D")
    assert tokens == [
        ProgressionToken("C", "chord"),
        ProgressionToken(",", "separator"),
        ProgressionToken("Am", "chord"),
        ProgressionToken(" - ", "separator"),
        ProgressionToken("Bb", "chord"),
        ProgressionToken(" | ", "separator"),
        ProgressionToken("D", "chord"),
    ]

def test_tokenize_progression_other():
    tokens = tokenize_progression("C xyz 1")
    assert tokens == [
        ProgressionToken("C", "chord"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("xyz", "other"),
        ProgressionToken(" ", "separator"),
        ProgressionToken("1", "nns"),
    ]

def test_tokenize_progression_empty():
    assert tokenize_progression("") == []
    assert tokenize_progression("   ") == [ProgressionToken("   ", "separator")]

def test_parse_input_key_extraction():
    # in C
    parsed = parse_input("in C")
    assert parsed.key_tonic == "C"
    assert parsed.key_mode is None

    # key: Am
    parsed = parse_input("key: Am")
    assert parsed.key_tonic == "A"
    assert parsed.key_mode == "Minor"

    # key: A minor
    parsed = parse_input("key: A minor")
    assert parsed.key_tonic == "A"
    assert parsed.key_mode == "Minor"

    # key: D aeolian
    parsed = parse_input("key: D aeolian")
    assert parsed.key_tonic == "D"
    assert parsed.key_mode == "Minor"

    # in Bb major
    parsed = parse_input("in Bb major")
    assert parsed.key_tonic == "Bb"
    assert parsed.key_mode == "Major"

def test_parse_input_mode_detection():
    # nns_to_chords (nns_hits > chord_hits)
    parsed = parse_input("1 4 5")
    assert parsed.mode == "nns_to_chords"

    # nns_to_chords (nns_hits and tonic)
    parsed = parse_input("1 4 5 in G")
    assert parsed.mode == "nns_to_chords"
    assert parsed.key_tonic == "G"

    # chords_to_nns (chord_hits > nns_hits)
    parsed = parse_input("C F G")
    assert parsed.mode == "chords_to_nns"

    # chords_to_nns (chord_hits > nns_hits, even if one NNS-like token is present)
    parsed = parse_input("C F 5")
    assert parsed.mode == "chords_to_nns"

def test_parse_input_text_preservation():
    input_text = "C F G in C"
    parsed = parse_input(input_text)
    assert parsed.text == input_text

def test_parse_input_empty():
    parsed = parse_input("")
    assert parsed.text == ""
    assert parsed.key_tonic is None
    assert parsed.key_mode is None
    assert parsed.mode == "chords_to_nns"

def test_parse_input_modes():
    # Minor modes
    for mode_str in ["minor", "aeolian", "Aeolian"]:
        parsed = parse_input(f"in C {mode_str}")
        assert parsed.key_mode == "Minor", f"Failed for {mode_str}"

    # Major modes
    for mode_str in ["major", "mode", "ionian", "dorian", "mixolydian", "lydian", "phrygian", "locrian"]:
        parsed = parse_input(f"in C {mode_str}")
        assert parsed.key_mode == "Major", f"Failed for {mode_str}"

    # Shorthand minor
    parsed = parse_input("in Cm")
    assert parsed.key_mode == "Minor"
    assert parsed.key_tonic == "C"

def test_parse_input_semicolon_newline():
    # Semicolon usage
    parsed = parse_input("key: G; 1 4 5")
    assert parsed.key_tonic == "G"
    assert parsed.mode == "nns_to_chords"

    # Newline usage
    parsed = parse_input("1 4 5\nin C")
    assert parsed.key_tonic == "C"
    assert parsed.mode == "nns_to_chords"

    # Text preservation
    assert parsed.text == "1 4 5\nin C"

def test_parse_input_tie_without_tonic():
    # 1 nns hit, 1 chord hit, no tonic
    parsed = parse_input("1 C")
    assert parsed.mode == "chords_to_nns"

    # tie with tonic
    parsed = parse_input("1 C in G")
    assert parsed.mode == "nns_to_chords"
