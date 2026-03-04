from __future__ import annotations

import runpy
from unittest.mock import patch

import pytest

from nashville_numbers.cli import main


def test_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["nns-convert", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "Usage: nns-convert [PROGRESSION]" in captured.out
        assert (
            "Convert between chord progressions and Nashville Number System (NNS)."
            in captured.out
        )


def test_short_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["nns-convert", "-h"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "Usage: nns-convert [PROGRESSION]" in captured.out


def test_args_conversion(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["nns-convert", "C", "-", "F", "-", "G"]):
        with patch(
            "nashville_numbers.cli.convert", return_value="1 - 4 - 5 in C"
        ) as mock_convert:
            main()
            mock_convert.assert_called_once_with("C - F - G")
            captured = capsys.readouterr()
            assert captured.out == "1 - 4 - 5 in C\n"


def test_stdin_tty_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["nns-convert"]):
        with patch("sys.stdin.isatty", return_value=True):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
            captured = capsys.readouterr()
            assert "Usage: nns-convert [PROGRESSION]" in captured.err


def test_stdin_not_tty_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["nns-convert"]):
        with patch("sys.stdin.isatty", return_value=False):
            with patch("sys.stdin.read", return_value="C - F - G \n"):
                with patch(
                    "nashville_numbers.cli.convert", return_value="1 - 4 - 5 in C"
                ) as mock_convert:
                    main()
                    mock_convert.assert_called_once_with("C - F - G")
                    captured = capsys.readouterr()
                    assert captured.out == "1 - 4 - 5 in C\n"


def test_main_execution() -> None:
    with patch("sys.argv", ["nns-convert", "--help"]):
        with pytest.raises(SystemExit) as exc:
            runpy.run_module("nashville_numbers.cli", run_name="__main__")
        assert exc.value.code == 0
