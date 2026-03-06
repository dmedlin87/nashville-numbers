"""Core conversion logic for chord<->NNS conversion."""

from __future__ import annotations

import re

from .output_contract import OutputBlock, build_output
from .key_inference import NOTE_TO_SEMITONE, infer_keys, infer_sections
from .parser import parse_input, tokenize_progression

SEMITONE_TO_DEGREE = {0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4", 6: "#4", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7"}
DEGREE_TO_SEMITONE = {
    "1": 0,
    "b2": 1,
    "2": 2,
    "b3": 3,
    "3": 4,
    "4": 5,
    "#4": 6,
    "5": 7,
    "b6": 8,
    "6": 9,
    "b7": 10,
    "7": 11,
}
DEGREE_TO_LETTER_OFFSET = {
    "1": 0,
    "b2": 1,
    "2": 1,
    "b3": 2,
    "3": 2,
    "4": 3,
    "#4": 3,
    "5": 4,
    "b6": 5,
    "6": 5,
    "b7": 6,
    "7": 6,
}
LETTER_TO_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LETTER_SEQUENCE = ("C", "D", "E", "F", "G", "A", "B")
SHARP_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
DEFAULT_NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
EXPLICIT_KEY_NORMALIZATION = {
    "Major": {
        "A#": "Bb",
        "D#": "Eb",
        "E#": "F",
        "Fb": "E",
        "G#": "Ab",
        "B#": "C",
    },
    "Minor": {
        "Cb": "B",
        "Db": "C#",
        "E#": "F",
        "Fb": "E",
        "Gb": "F#",
        "B#": "C",
    },
}

MAJOR_DIATONIC = {"1": "", "2": "m", "3": "m", "4": "", "5": "", "6": "m", "7": "dim"}
MINOR_DIATONIC = {"1": "m", "2": "dim", "b3": "", "4": "m", "5": "m", "b6": "", "b7": ""}

CHORD_RE = re.compile(r"^([A-G](?:#|b)?)([^/]*)?(?:/([A-G](?:#|b)?))?$")
DEGREE_RE = re.compile(r"^([#b]?[1-7])((?:m|dim|aug|sus2|sus4)?)((?:\([^)]*\)|(?:maj7|mmaj7|7|6|9|11|13|add\d+|[#b]\d+)*)?)(?:/([#b]?[1-7]))?$", re.IGNORECASE)
EXT_TOKENS_RE = re.compile(r"(?:add\d+|[#b]\d+|6|7|9|11|13|alt)", flags=re.IGNORECASE)


def convert(input_text: str) -> str:
    parsed = parse_input(input_text)

    if parsed.mode == "nns_to_chords":
        if not parsed.key_tonic:
            return "Key: REQUIRED"
        tonic, mode = _normalize_explicit_key(parsed.key_tonic, parsed.key_mode or "Major")
        converted = _convert_nns_to_chords(parsed.progression_text, tonic, mode)
        return build_output([OutputBlock(tonic, mode, converted)])

    if parsed.key_tonic:
        tonic, mode = _normalize_explicit_key(parsed.key_tonic, parsed.key_mode or "Major")
        converted = _convert_chords_to_nns(parsed.progression_text, tonic, mode)
        return build_output([OutputBlock(tonic, mode, converted)])

    progression = parsed.progression_text
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
    return parse_input(text).progression_text


def _normalize_explicit_key(tonic: str, mode: str) -> tuple[str, str]:
    return EXPLICIT_KEY_NORMALIZATION.get(mode, {}).get(tonic, tonic), mode


def _convert_chords_to_nns(prog: str, tonic: str, mode: str) -> str:
    t = NOTE_TO_SEMITONE.get(tonic, 0)
    degree_map = SEMITONE_TO_DEGREE
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

    suffix, extension, lower = _extract_base_quality(compact, lower)
    extension, lower = _extract_major_extension(compact, lower, extension)
    extension = _extract_other_extensions(compact, lower, extension)
    suffix = _apply_diatonic_defaults(suffix, degree, mode, quality_raw, lower)

    return suffix, extension


def _extract_base_quality(compact: str, lower: str) -> tuple[str, str, str]:
    if "ø" in compact or "m7b5" in lower:
        return "m", "7b5", lower.replace("ø", "").replace("m7b5", "")
    if "dim" in lower or "°" in compact:
        return "dim", "", lower.replace("dim", "").replace("°", "")
    if "aug" in lower or "+" in compact:
        return "aug", "", lower.replace("aug", "").replace("+", "")
    if "sus2" in lower:
        return "sus2", "", lower.replace("sus2", "")
    if "sus4" in lower or "sus" in lower:
        return "sus4", "", lower.replace("sus4", "").replace("sus", "")
    if lower.startswith("mmaj"):
        return "m", "maj7", lower[5:]
    if lower.startswith("min"):
        return "m", "", lower[3:]
    if lower.startswith("m") and not lower.startswith("maj"):
        return "m", "", lower[1:]
    return "", "", lower


def _extract_major_extension(compact: str, lower: str, extension: str) -> tuple[str, str]:
    if lower.startswith("maj7") or compact.startswith("M7"):
        return extension or "maj7", lower.replace("maj7", "", 1)
    if lower.startswith("maj") or compact.startswith("M"):
        return extension, lower[3:] if lower.startswith("maj") else lower
    return extension, lower


def _extract_other_extensions(compact: str, lower: str, extension: str) -> str:
    paren = re.search(r"\(([^)]*)\)", compact)
    if paren:
        ext_val = paren.group(1).strip()
        if ext_val:
            return ext_val
    else:
        merged = "".join(EXT_TOKENS_RE.findall(lower))
        if extension and merged and merged not in extension:
            return extension + merged
        if merged and not extension:
            return merged
    return extension


def _apply_diatonic_defaults(suffix: str, degree: str, mode: str, quality_raw: str, lower: str) -> str:
    if not suffix:
        defaults = MINOR_DIATONIC if mode == "Minor" else MAJOR_DIATONIC
        suffix = defaults.get(degree, "")

    if mode == "Minor" and degree == "5":
        if not quality_raw.strip():
            return ""
        if any(token in lower for token in ("7", "9", "11", "13", "alt")):
            return ""
        if quality_raw.strip() and not lower.startswith("m") and not lower.startswith("min"):
            return ""

    return suffix


def _convert_nns_to_chords(prog: str, tonic: str, mode: str) -> str:
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
        root = _degree_to_note(degree, tonic)
        chord = root + _suffix_to_chord_quality(suffix, degree, mode) + _normalize_extension_for_chord(ext_raw)
        if bass:
            chord += f"/{_degree_to_note(bass, tonic)}"
        out.append(token.text.replace(stripped, chord))

    return "".join(out) if out else prog


def _normalize_extension_for_chord(ext_raw: str) -> str:
    if not ext_raw:
        return ""
    if ext_raw.startswith("(") and ext_raw.endswith(")"):
        return ext_raw
    return f"({ext_raw})"


def _degree_to_note(degree: str, tonic: str) -> str:
    semitone_step = DEGREE_TO_SEMITONE.get(degree)
    letter_offset = DEGREE_TO_LETTER_OFFSET.get(degree)
    tonic_semitone = NOTE_TO_SEMITONE.get(tonic)
    if semitone_step is None or letter_offset is None or tonic_semitone is None:
        return tonic

    semitone = (tonic_semitone + semitone_step) % 12
    tonic_letter = tonic[0]
    tonic_letter_index = LETTER_SEQUENCE.index(tonic_letter)
    target_letter = LETTER_SEQUENCE[(tonic_letter_index + letter_offset) % len(LETTER_SEQUENCE)]
    natural_semitone = LETTER_TO_SEMITONE[target_letter]
    accidental_delta = (semitone - natural_semitone + 12) % 12
    if accidental_delta > 6:
        accidental_delta -= 12

    if accidental_delta == -1:
        return f"{target_letter}b"
    if accidental_delta == 0:
        return target_letter
    if accidental_delta == 1:
        return f"{target_letter}#"
    return _fallback_note_name(semitone, tonic)


def _fallback_note_name(semitone: int, tonic: str) -> str:
    if "b" in tonic:
        return FLAT_NOTE_NAMES[semitone]
    if "#" in tonic:
        return SHARP_NOTE_NAMES[semitone]
    return DEFAULT_NOTE_NAMES[semitone]


def _suffix_to_chord_quality(suffix: str, degree: str, mode: str) -> str:
    if suffix:
        return suffix
    defaults = MINOR_DIATONIC if mode == "Minor" else MAJOR_DIATONIC
    return defaults.get(degree, "")
