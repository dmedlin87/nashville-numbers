"""CLI entrypoint for nashville number conversion."""

from __future__ import annotations

import sys

from .converter import convert


def main() -> None:
    if len(sys.argv) > 1:
        input_text = " ".join(sys.argv[1:])
    else:
        input_text = sys.stdin.read().strip()
    print(convert(input_text))


if __name__ == "__main__":
    main()
