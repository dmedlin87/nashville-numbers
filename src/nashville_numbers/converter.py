"""Core conversion logic for chord<->NNS conversion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .formatting import ConversionBlock, format_key_line, render_blocks
from .parser import parse_input

NOTE_TO_SEMITONE = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}

SEMITONE_TO_DEGREE_MAJOR = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "#4", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7"}
SEMITONE_TO_DEGREE_MINOR = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "#4", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7"}

MAJOR_DIATONIC = {"1": "", "2": "m", "3": "m", "4": "", "5": "", "6": "m", "7": "dim"}
MINOR_DIATONIC = {"1": "m", "2": "dim", "b3": "", "4": "m", "5": "m", "b6": "", "b7": ""}

TOKEN_SPLIT_RE = re.compile(r"(\s*-\s*|\s*,\s*|\|)")
CHORD_RE = re.compile(r"^([A-G](?:#|b)?)([^/]*)?(?:/([A-G](?:#|b)?))?$")
DEGREE_RE = re.compile(r"^([#b]?[1-7])((?:m|dim|aug|sus2|sus4|)?)((?:\([^)]*\))?)(?:/([#b]?[1-7]))?$")


@dataclass(frozen=True)
class KeyChoice:
    tonic: str
    mode: str


def convert(input_text: str) -> str:
    parsed = parse_input(input_text)

    if parsed.mode == "nns_to_chords":
        if not parsed.key_tonic:
            return "Key: REQUIRED"
        mode = parsed.key_mode or "Major"
        progression = _extract_progression(parsed.text)
        converted = _convert_nns_to_chords(progression, parsed.key_tonic, mode)
        return render_blocks([ConversionBlock(format_key_line(parsed.key_tonic, mode), f"{converted} ({progression})")])

    progression = _extract_progression(parsed.text)
    if parsed.key_tonic:
        mode = parsed.key_mode or "Major"
        converted = _convert_chords_to_nns(progression, parsed.key_tonic, mode)
        return render_blocks([ConversionBlock(format_key_line(parsed.key_tonic, mode), f"{converted} ({progression})")])

    choices = _infer_keys(progression)
    blocks = []
    for choice in choices:
        converted = _convert_chords_to_nns(progression, choice.tonic, choice.mode)
        blocks.append(ConversionBlock(format_key_line(choice.tonic, choice.mode), f"{converted} ({progression})"))
    return render_blocks(blocks)


def _extract_progression(text: str) -> str:
    cleaned = re.sub(r"\b(?:in|key\s*:)[^;\n]+", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace(";", " ").strip()
    return cleaned


def _infer_keys(prog: str) -> list[KeyChoice]:
    roots = [m.group(1) for t in _split_tokens(prog) if (m := CHORD_RE.match(t.strip()))]
    if not roots:
        return [KeyChoice("C", "Major")]

    candidates: list[tuple[int, str, str]] = []
    tonics = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    major_scale = {0, 2, 4, 5, 7, 9, 11}
    minor_scale = {0, 2, 3, 5, 7, 8, 10}

    for tonic in tonics:
        t = NOTE_TO_SEMITONE[tonic]
        maj_score = sum(1 for r in roots if (NOTE_TO_SEMITONE.get(r, -1) - t) % 12 in major_scale)
        min_score = sum(1 for r in roots if (NOTE_TO_SEMITONE.get(r, -1) - t) % 12 in minor_scale)
        candidates.append((maj_score, tonic, "Major"))
        candidates.append((min_score, tonic, "Minor"))

    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[:3]

    if best and best[0][2] == "Major":
        rel_minor = _relative_minor(best[0][1])
        rel_tuple = next((c for c in candidates if c[1] == rel_minor and c[2] == "Minor"), None)
        if rel_tuple and rel_tuple not in best and rel_tuple[0] >= best[0][0] - 1:
            best = [best[0], rel_tuple, *best[1:2]][:3]

    return [KeyChoice(t, m) for _, t, m in best]


def _relative_minor(major: str) -> str:
    semitone = (NOTE_TO_SEMITONE[major] + 9) % 12
    for name, val in NOTE_TO_SEMITONE.items():
        if len(name) <= 2 and val == semitone and "b" not in name:
            return name
    return "A"


def _split_tokens(prog: str) -> list[str]:
    return [p for p in TOKEN_SPLIT_RE.split(prog) if p != ""]


def _convert_chords_to_nns(prog: str, tonic: str, mode: str) -> str:
    t = NOTE_TO_SEMITONE.get(tonic, 0)
    out = []
    for tok in _split_tokens(prog):
        stripped = tok.strip()
        m = CHORD_RE.match(stripped)
        if not m:
            out.append(tok)
            continue
        root, quality_raw, bass = m.group(1), (m.group(2) or ""), m.group(3)
        if root not in NOTE_TO_SEMITONE:
            out.append(tok)
            continue
        degree_map = SEMITONE_TO_DEGREE_MINOR if mode == "Minor" else SEMITONE_TO_DEGREE_MAJOR
        degree = degree_map[(NOTE_TO_SEMITONE[root] - t) % 12]
        nns = degree + _quality_to_nns_suffix(degree, quality_raw, mode)
        nns += _extensions_to_parenthetical(quality_raw)
        if bass and bass in NOTE_TO_SEMITONE:
            bass_degree = degree_map[(NOTE_TO_SEMITONE[bass] - t) % 12]
            nns += f"/{bass_degree}"
        out.append(tok.replace(stripped, nns))
    return "".join(out)


def _quality_to_nns_suffix(degree: str, quality_raw: str, mode: str) -> str:
    q = quality_raw.lower()
    if "dim" in q or "°" in q:
        return "dim"
    if "aug" in q or "+" in q:
        return "aug"
    if "sus2" in q:
        return "sus2"
    if "sus4" in q or "sus" in q:
        return "sus4"
    if q.startswith("m") and not q.startswith("maj"):
        return "m"

    defaults = MINOR_DIATONIC if mode == "Minor" else MAJOR_DIATONIC
    return defaults.get(degree, "")


def _extensions_to_parenthetical(quality_raw: str) -> str:
    q = quality_raw
    if not q:
        return ""
    paren_match = re.search(r"\(([^)]*)\)", q)
    if paren_match:
        return f"({paren_match.group(1)})"
    ext_match = re.search(r"(maj7|mmaj7|7|6|9|11|13|add\d+|[#b]\d+)", q, flags=re.IGNORECASE)
    return f"({ext_match.group(1)})" if ext_match else ""


def _convert_nns_to_chords(prog: str, tonic: str, mode: str) -> str:
    t = NOTE_TO_SEMITONE.get(tonic, 0)
    out = []
    for tok in _split_tokens(prog):
        stripped = tok.strip()
        m = DEGREE_RE.match(stripped)
        if not m:
            out.append(tok)
            continue
        degree, suffix, ext, bass = m.groups()
        root = _degree_to_note(degree, t)
        chord = root + _suffix_to_chord_quality(suffix, degree, mode) + ext
        if bass:
            chord += f"/{_degree_to_note(bass, t)}"
        out.append(tok.replace(stripped, chord))
    return "".join(out)


def _degree_to_note(degree: str, tonic_semitone: int) -> str:
    steps = {"1": 0, "b2": 1, "2": 2, "b3": 3, "3": 4, "4": 5, "#4": 6, "5": 7, "b6": 8, "6": 9, "b7": 10, "7": 11}
    semitone = (tonic_semitone + steps.get(degree, 0)) % 12
    preferred = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return preferred[semitone]


def _suffix_to_chord_quality(suffix: str, degree: str, mode: str) -> str:
    if suffix:
        return suffix.replace("dim", "dim")
    defaults = MINOR_DIATONIC if mode == "Minor" else MAJOR_DIATONIC
    return defaults.get(degree, "")
