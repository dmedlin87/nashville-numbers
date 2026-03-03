"""CLI entrypoint for nashville number conversion."""

from __future__ import annotations

import os
import sys

from .converter import convert


_HELP = """\
Usage: nns-convert [PROGRESSION]

Convert between chord progressions and Nashville Number System (NNS).
Mode is detected automatically from the input.

CHORDS → NNS  (key is inferred; or pin it with "in KEY"):
  nns-convert "C - F - G"
  nns-convert "Am - F - C - G"
  nns-convert "| C | F G | Am |"
  nns-convert "Cmaj7#11/G, Dm7, G7"
  nns-convert "C - F - G in C"         (explicit key, one result)

NNS → CHORDS  (key required via "in KEY" or "Key: KEY"):
  nns-convert "1 - 4 - 5 in G"
  nns-convert "Key: Eb Major; 1 6 2 5"
  nns-convert "1m - b7 - 4m - 5(7) in A minor"

Via stdin:
  echo "C - F - G" | nns-convert
  cat chords.txt | nns-convert

Output format:
  Key: <Tonic> <Mode>
  <converted progression>

  When the key is ambiguous, up to 3 candidate interpretations are shown,
  each separated by a blank line. Supply an explicit key to get one result.

  NNS input without a key outputs:
    Key: REQUIRED
  and exits with status 1.

Color output is enabled automatically when writing to a terminal.
Set NO_COLOR=1 or pipe the output to disable it.
"""

_KEY_COLOR = "\033[1;36m"  # bold cyan
_RESET = "\033[0m"


def _use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _colorize(text: str) -> str:
    """Highlight 'Key:' header lines in bold cyan for terminal readability."""
    lines = []
    for line in text.split("\n"):
        if line.startswith("Key:"):
            lines.append(f"{_KEY_COLOR}{line}{_RESET}")
        else:
            lines.append(line)
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ("-h", "--help"):
            print(_HELP, end="")
            sys.exit(0)
        if arg in ("-V", "--version"):
            from importlib.metadata import version
            print(f"nns-convert {version('nashville-numbers')}")
            sys.exit(0)
        input_text = " ".join(sys.argv[1:])
    else:
        if sys.stdin.isatty():
            print("Usage: nns-convert [PROGRESSION]", file=sys.stderr)
            print("Run 'nns-convert --help' for more information.", file=sys.stderr)
            sys.exit(1)
        input_text = sys.stdin.read().strip()

    if not input_text.strip():
        print("Error: no input provided. Run 'nns-convert --help' for usage.", file=sys.stderr)
        sys.exit(1)

    result = convert(input_text)

    if result == "Key: REQUIRED":
        print(result)
        sys.exit(1)

    print(_colorize(result) if _use_color() else result)


if __name__ == "__main__":
    main()
