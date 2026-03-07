import sys
import io
import pytest
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

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Input exceeds maximum length of 5 characters.\n"
