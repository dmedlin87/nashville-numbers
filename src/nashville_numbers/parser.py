"""Input parsing and mode detection for Nashville converter."""

from __future__ import annotations

import re
from dataclasses import dataclass

KEY_RE = re.compile(
    r"(?:\b(?:in|key\s*:)\s*)([A-G](?:#|b)?)(?:\s*(major|minor|mode|ionian|aeolian|dorian|mixolydian|lydian|phrygian|locrian))?",
    re.IGNORECASE,
)

SEPARATOR_CHARS = set(" \t\n\r,-|")
NNS_TOKEN_RE = re.compile(
    r"^[#b]?[1-7](?:m|dim|aug|sus2|sus4)?(?:\([^)]*\)|(?:maj7|mmaj7|7|6|9|11|13|add\d+|[#b]\d+)*)?(?:/[#b]?[1-7])?$",
    re.IGNORECASE,
)
CHORD_TOKEN_RE = re.compile(
    r"^[A-G](?:#|b)?(?:"
    r"(?:maj|M|min|m|dim|°|ø|aug|\+|sus2|sus4|sus)?"
    r"(?:maj7|mmaj7|add\d+|[#b]\d+|6|7|9|11|13|alt|\([^)]*\))*"
    r")?(?:/[A-G](?:#|b)?)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProgressionToken:
    text: str
    kind: str


@dataclass(frozen=True)
class ParsedInput:
    mode: str
    text: str
    key_tonic: str | None
    key_mode: str | None


def tokenize_progression(text: str) -> list[ProgressionToken]:
    tokens: list[ProgressionToken] = []
    idx = 0
    while idx < len(text):
        if text[idx] in SEPARATOR_CHARS:
            end = idx
            while end < len(text) and text[end] in SEPARATOR_CHARS:
                end += 1
            tokens.append(ProgressionToken(text[idx:end], "separator"))
            idx = end
            continue

        end = idx
        while end < len(text) and text[end] not in SEPARATOR_CHARS:
            end += 1
        chunk = text[idx:end]
        if NNS_TOKEN_RE.fullmatch(chunk):
            kind = "nns"
        elif CHORD_TOKEN_RE.fullmatch(chunk):
            kind = "chord"
        else:
            kind = "other"
        tokens.append(ProgressionToken(chunk, kind))
        idx = end
    return tokens


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

    progression = re.sub(r"\b(?:in|key\s*:)[^;\n]+", "", text, flags=re.IGNORECASE).replace(";", " ").strip()
    tokens = tokenize_progression(progression)
    nns_hits = sum(1 for token in tokens if token.kind == "nns")
    chord_hits = sum(1 for token in tokens if token.kind == "chord")

    detected_mode = "nns_to_chords" if (nns_hits > chord_hits or (nns_hits and tonic)) else "chords_to_nns"

    return ParsedInput(mode=detected_mode, text=text, key_tonic=tonic, key_mode=mode)
