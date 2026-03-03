"""Core conversion logic for chord<->NNS conversion."""

from __future__ import annotations

import re

from .output_contract import OutputBlock, build_output
from .key_inference import KeyChoice, NOTE_TO_SEMITONE, infer_keys, infer_sections
from .parser import parse_input, tokenize_progression

SEMITONE_TO_DEGREE_MAJOR = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "#4", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7"}
SEMITONE_TO_DEGREE_MINOR = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "#4", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7"}

MAJOR_DIATONIC = {"1": "", "2": "m", "3": "m", "4": "", "5": "", "6": "m", "7": "dim"}
MINOR_DIATONIC = {"1": "m", "2": "dim", "b3": "", "4": "m", "5": "m", "b6": "", "b7": ""}

CHORD_RE = re.compile(r"^([A-G](?:#|b)?)([^/]*)?(?:/([A-G](?:#|b)?))?$")
DEGREE_RE = re.compile(r"^([#b]?[1-7])((?:m|dim|aug|sus2|sus4)?)((?:\([^)]*\)|(?:maj7|mmaj7|7|6|9|11|13|add\d+|[#b]\d+)*)?)(?:/([#b]?[1-7]))?$", re.IGNORECASE)


def convert(input_text: str) -> str:
    parsed = parse_input(input_text)

    if parsed.mode == "nns_to_chords":
        if not parsed.key_tonic:
            return "Key: REQUIRED"
        mode = parsed.key_mode or "Major"
        progression = _extract_progression(parsed.text)
        converted = _convert_nns_to_chords(progression, parsed.key_tonic, mode)
        return build_output([OutputBlock(parsed.key_tonic, mode, converted)])

    progression = _extract_progression(parsed.text)
    if parsed.key_tonic:
        mode = parsed.key_mode or "Major"
        converted = _convert_chords_to_nns(progression, parsed.key_tonic, mode)
        return build_output([OutputBlock(parsed.key_tonic, mode, converted)])

    sections = infer_sections(progression)
    blocks: list[OutputBlock] = []
    if len(sections) > 1:
        for section_text, choice in sections:
            converted = _convert_chords_to_nns(section_text, choice.tonic, choice.mode)
            blocks.append(OutputBlock(choice.tonic, choice.mode, converted))
    else:
        choices = infer_keys(progression)
        for choice in choices:
            converted = _convert_chords_to_nns(progression, choice.tonic, choice.mode)
            blocks.append(OutputBlock(choice.tonic, choice.mode, converted))
    return build_output(blocks)


def _extract_progression(text: str) -> str:
    cleaned = re.sub(r"\b(?:in|key\s*:)[^;\n]+", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace(";", " ").strip()
    return cleaned


def _convert_chords_to_nns(prog: str, tonic: str, mode: str) -> str:
    t = NOTE_TO_SEMITONE.get(tonic, 0)
    degree_map = SEMITONE_TO_DEGREE_MINOR if mode == "Minor" else SEMITONE_TO_DEGREE_MAJOR
    out: list[str] = []

    for token in tokenize_progression(prog):
        if token.kind == "separator":
            out.append(token.text)
            continue
        if token.kind != "chord":
            out.append(token.text)
            continue

        stripped = token.text.strip()
        m = CHORD_RE.match(stripped)
        if not m:
            out.append(token.text)
            continue

        root, quality_raw, bass = m.group(1), (m.group(2) or ""), m.group(3)
        if root not in NOTE_TO_SEMITONE:
            out.append(token.text)
            continue

        degree = degree_map[(NOTE_TO_SEMITONE[root] - t) % 12]
        suffix, extension = _parse_chord_quality(root, quality_raw, degree, mode)
        nns = degree + suffix
        if extension:
            nns += f"({extension})"
        if bass and bass in NOTE_TO_SEMITONE:
            bass_degree = degree_map[(NOTE_TO_SEMITONE[bass] - t) % 12]
            nns += f"/{bass_degree}"
        out.append(token.text.replace(stripped, nns))

    return "".join(out) if out else prog


def _parse_chord_quality(_root: str, quality_raw: str, degree: str, mode: str) -> tuple[str, str]:
    raw = quality_raw.strip()
    compact = raw.replace(" ", "")
    lower = compact.lower()

    suffix = ""
    extension = ""

    if "ø" in compact or "m7b5" in lower:
        suffix = "m"
        extension = "7b5"
        lower = lower.replace("ø", "").replace("m7b5", "")
    elif "dim" in lower or "°" in compact:
        suffix = "dim"
        lower = lower.replace("dim", "").replace("°", "")
    elif "aug" in lower or "+" in compact:
        suffix = "aug"
        lower = lower.replace("aug", "").replace("+", "")
    elif "sus2" in lower:
        suffix = "sus2"
        lower = lower.replace("sus2", "")
    elif "sus4" in lower or "sus" in lower:
        suffix = "sus4"
        lower = lower.replace("sus4", "").replace("sus", "")
    elif lower.startswith("mmaj"):
        suffix = "m"
        extension = "maj7"
        lower = lower[5:]
    elif lower.startswith("min"):
        suffix = "m"
        lower = lower[3:]
    elif lower.startswith("m") and not lower.startswith("maj"):
        suffix = "m"
        lower = lower[1:]

    if lower.startswith("maj7") or compact.startswith("M7"):
        extension = extension or "maj7"
        lower = lower.replace("maj7", "", 1)
    elif lower.startswith("maj") or compact.startswith("M"):
        lower = lower[3:] if lower.startswith("maj") else lower

    paren = re.search(r"\(([^)]*)\)", compact)
    if paren:
        ext_val = paren.group(1).strip()
        if ext_val:
            extension = ext_val
    else:
        ext_tokens = re.findall(r"(?:add\d+|[#b]\d+|6|7|9|11|13|alt)", lower, flags=re.IGNORECASE)
        merged = "".join(ext_tokens)
        if extension and merged and merged not in extension:
            extension = extension + merged
        elif merged and not extension:
            extension = merged

    if not suffix:
        defaults = MINOR_DIATONIC if mode == "Minor" else MAJOR_DIATONIC
        suffix = defaults.get(degree, "")

    if mode == "Minor" and degree == "5":
        if quality_raw.strip() == "":
            suffix = ""
        elif any(token in lower for token in ("7", "9", "11", "13", "alt")):
            suffix = ""
        elif quality_raw.strip() and not lower.startswith("m") and not lower.startswith("min"):
            suffix = ""

    return suffix, extension


def _convert_nns_to_chords(prog: str, tonic: str, mode: str) -> str:
    t = NOTE_TO_SEMITONE.get(tonic, 0)
    out: list[str] = []

    for token in tokenize_progression(prog):
        if token.kind == "separator":
            out.append(token.text)
            continue

        stripped = token.text.strip()
        m = DEGREE_RE.match(stripped)
        if not m:
            out.append(token.text)
            continue

        degree, suffix, ext_raw, bass = m.groups()
        root = _degree_to_note(degree, t)
        chord = root + _suffix_to_chord_quality(suffix, degree, mode) + _normalize_extension_for_chord(ext_raw)
        if bass:
            chord += f"/{_degree_to_note(bass, t)}"
        out.append(token.text.replace(stripped, chord))

    return "".join(out) if out else prog


def _normalize_extension_for_chord(ext_raw: str) -> str:
    if not ext_raw:
        return ""
    if ext_raw.startswith("(") and ext_raw.endswith(")"):
        return ext_raw
    return f"({ext_raw})"


def _degree_to_note(degree: str, tonic_semitone: int) -> str:
    steps = {"1": 0, "b2": 1, "2": 2, "b3": 3, "3": 4, "4": 5, "#4": 6, "5": 7, "b6": 8, "6": 9, "b7": 10, "7": 11}
    semitone = (tonic_semitone + steps.get(degree, 0)) % 12
    preferred = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return preferred[semitone]


def _suffix_to_chord_quality(suffix: str, degree: str, mode: str) -> str:
    if suffix:
        return suffix
    defaults = MINOR_DIATONIC if mode == "Minor" else MAJOR_DIATONIC
    return defaults.get(degree, "")
