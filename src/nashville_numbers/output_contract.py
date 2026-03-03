"""Build final responses that follow the strict output contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputBlock:
    tonic: str
    mode: str
    progression: str


def build_output(blocks: list[OutputBlock]) -> str:
    """Render one or more key/progression blocks.

    Each block renders as:
      Key: <Tonic> <Mode>
      <converted progression>
    Blocks are separated by a blank line.
    """

    return "\n\n".join(f"{_format_key_line(block.tonic, block.mode)}\n{block.progression}" for block in blocks)


def _format_key_line(tonic: str, mode: str) -> str:
    return f"Key: {tonic} {mode}"
