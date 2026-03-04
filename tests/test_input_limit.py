import sys
import io
from nashville_numbers import cli

def test_stdin_read_limit(monkeypatch, capsys):
    # Set a very small limit for testing
    test_limit = 5
    monkeypatch.setattr(cli, "MAX_INPUT_LENGTH", test_limit)

    # "C F G Bb" is 8 characters
    mock_stdin = io.StringIO("C F G Bb")
    monkeypatch.setattr(sys, "stdin", mock_stdin)

    # Mock sys.argv to have no arguments so it reads from stdin
    monkeypatch.setattr(sys, "argv", ["nns-convert"])

    # Mock isatty to return False so it reads from stdin
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    # Run main
    cli.main()

    captured = capsys.readouterr()

    # If it only reads 5 characters, it reads "C F G"
    # In C Major, "C F G" -> "1 4 5"
    # "Bb" would be "b7", so "b7" should NOT be in the output if truncated.

    assert "1 4 5" in captured.out
    assert "b7" not in captured.out
