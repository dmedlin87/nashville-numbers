import re
import time
import pytest
from nashville_numbers.parser import NNS_TOKEN_RE, CHORD_TOKEN_RE

@pytest.mark.parametrize("regex, prefix", [
    (NNS_TOKEN_RE, "1add"),
    (CHORD_TOKEN_RE, "Cadd"),
])
def test_regex_backtracking_performance(regex, prefix):
    """
    Ensure regexes do not exhibit exponential backtracking on large non-matching inputs.
    A vulnerable regex would take several seconds for length 5000.
    """
    payload = prefix + "7" * 5000 + "!"
    start = time.time()
    regex.fullmatch(payload)
    end = time.time()
    elapsed = end - start

    # Secure regex should be nearly instantaneous (< 10ms)
    assert elapsed < 0.1, f"Regex {regex.pattern} took too long: {elapsed:.4f}s"

@pytest.mark.parametrize("regex, cases", [
    (NNS_TOKEN_RE, ["1", "1m", "1maj7", "1(add9)", "1/5", "1add9", "1#5", "1b5", "1add11", "1add13", "1add9#11"]),
    (CHORD_TOKEN_RE, ["C", "Cm", "Cmaj7", "C(add9)", "C/G", "Cadd9", "C#5", "Cb5", "C7alt"]),
])
def test_regex_correctness(regex, cases):
    for tc in cases:
        assert regex.fullmatch(tc), f"Regex {regex.pattern} failed to match valid input {tc}"
