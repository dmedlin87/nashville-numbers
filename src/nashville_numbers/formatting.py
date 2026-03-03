"""Output formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversionBlock:
    key_line: str
    progression_line: str


def format_key_line(tonic: str, mode: str) -> str:
    return f"Key: {tonic} {mode}"


def render_blocks(blocks: list[ConversionBlock]) -> str:
    return "\n\n".join(f"{b.key_line}\n{b.progression_line}" for b in blocks)
