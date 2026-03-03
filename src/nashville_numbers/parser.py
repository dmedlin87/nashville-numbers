"""Input parsing and mode detection for Nashville converter."""

from __future__ import annotations

import re
from dataclasses import dataclass

KEY_RE = re.compile(
    r"(?:\b(?:in|key\s*:)\s*)([A-G](?:#|b)?)(?:\s*(major|minor|mode|ionian|aeolian|dorian|mixolydian|lydian|phrygian|locrian))?",
    re.IGNORECASE,
)

NNS_TOKEN_RE = re.compile(r"\b[#b]?[1-7](?:m|dim|aug|sus2|sus4)?(?:\([^)]*\))?(?:/[#b]?[1-7])?\b")
CHORD_TOKEN_RE = re.compile(r"\b[A-G](?:#|b)?(?:maj|min|m|dim|aug|sus|add|M)?[\w#+\-°ø()]*?(?:/[A-G](?:#|b)?)?\b")


@dataclass(frozen=True)
class ParsedInput:
    mode: str
    text: str
    key_tonic: str | None
    key_mode: str | None


def parse_input(input_text: str) -> ParsedInput:
    text = input_text.strip()
    key_match = KEY_RE.search(text)
    tonic = None
    mode = None
    if key_match:
        tonic = key_match.group(1)
        raw_mode = key_match.group(2)
        if raw_mode:
            mode = "Minor" if raw_mode.lower().startswith("min") or raw_mode.lower() == "aeolian" else "Major"

    nns_hits = len(NNS_TOKEN_RE.findall(text))
    chord_hits = len(CHORD_TOKEN_RE.findall(text))

    detected_mode = "nns_to_chords" if (nns_hits > chord_hits or (nns_hits and tonic)) else "chords_to_nns"

    return ParsedInput(mode=detected_mode, text=text, key_tonic=tonic, key_mode=mode)
