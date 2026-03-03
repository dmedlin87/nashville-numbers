"""CLI entrypoint for nashville number conversion."""

from __future__ import annotations

import sys

from .converter import convert


def main() -> None:
    if len(sys.argv) > 1:
        if sys.argv[1] in ("-h", "--help"):
            print("Usage: nns-convert [PROGRESSION]")
            print()
            print("Convert between chord progressions and Nashville Number System (NNS).")
            print()
            print("Examples:")
            print('  nns-convert "C - F - G"')
            print('  nns-convert "1 - 4 - 5 in G"')
            print('  echo "C - F - G" | nns-convert')
            sys.exit(0)
        input_text = " ".join(sys.argv[1:])
    else:
        if sys.stdin.isatty():
            print("Usage: nns-convert [PROGRESSION]", file=sys.stderr)
            print("Run 'nns-convert --help' for more information.", file=sys.stderr)
            sys.exit(1)
        input_text = sys.stdin.read().strip()
    print(convert(input_text))


if __name__ == "__main__":
    main()
