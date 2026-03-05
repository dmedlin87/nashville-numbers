from __future__ import annotations

from nashville_numbers.output_contract import OutputBlock, _format_key_line, build_output


def test_format_key_line() -> None:
    assert _format_key_line("Bb", "Minor") == "Key: Bb Minor"


def test_build_output_single_block() -> None:
    blocks = [OutputBlock("C", "Major", "1 - 4 - 5")]
    assert build_output(blocks) == "Key: C Major\n1 - 4 - 5"


def test_build_output_multiple_blocks_are_separated_by_blank_line() -> None:
    blocks = [
        OutputBlock("C", "Major", "1 - 4 - 5"),
        OutputBlock("A", "Minor", "1m - b7 - 4m"),
    ]
    assert build_output(blocks) == (
        "Key: C Major\n1 - 4 - 5\n\n"
        "Key: A Minor\n1m - b7 - 4m"
    )


def test_build_output_with_no_blocks_returns_empty_string() -> None:
    assert build_output([]) == ""

