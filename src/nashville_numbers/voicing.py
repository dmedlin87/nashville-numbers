"""Chord voicing helpers — Python port of the JS chord voicing in gui.py."""

from __future__ import annotations

import re
from typing import Any

from .converter import DEGREE_TO_SEMITONE
from .key_inference import NOTE_TO_SEMITONE

# Regex that strips quality suffixes before looking up the root note name.
# Mirrors the JS getNoteValue cleanup regex exactly.
_QUALITY_STRIP_RE = re.compile(
    r"maj7|mmaj7|min|maj|dim|aug|sus2|sus4|m|7|6|9|11|13|add\d+|[#b]\d+",
    re.IGNORECASE,
)

_CHORD_ROOT_RE = re.compile(r"^[A-G](?:#|b)?")

# NNS degree regex — matches a leading accidental + digit (e.g. "b3", "#4", "6").
_NNS_DEGREE_RE = re.compile(r"^[#b]?[1-7]")

# Slash-chord bass note regex.
_SLASH_BASS_RE = re.compile(r"/([A-G](?:#|b)?)")


def get_note_value(name: str) -> int:
    """Note name → pitch class 0-11. Strips quality suffixes before lookup."""
    stripped = _QUALITY_STRIP_RE.sub("", name)
    return NOTE_TO_SEMITONE.get(stripped, 0)


def extract_chord_root(text: str) -> str | None:
    """Extract leading note name from a chord string (e.g. 'Am7' → 'A')."""
    m = _CHORD_ROOT_RE.match(str(text or ""))
    return m.group(0) if m else None


def slot_to_chord_data(slot: dict[str, Any]) -> dict[str, Any]:
    """Extract chord info from a plan slot dict.

    Returns a dict with keys: type, text, root, key_tonic, key_mode.
    """
    return {
        "type": "chord",
        "text": slot["chord"],
        "root": extract_chord_root(slot["chord"]),
        "key_tonic": slot["key"]["tonic"],
        "key_mode": slot["key"]["mode"],
    }


def get_chord_root_value(chord_data: dict[str, Any], key: dict[str, str]) -> int:
    """Root pitch class 0-11. Handles NNS degree-to-pitch conversion."""
    if chord_data.get("type") == "nns":
        m = _NNS_DEGREE_RE.match(str(chord_data.get("text", "")))
        degree = m.group(0) if m else "1"
        return (get_note_value(key["tonic"]) + DEGREE_TO_SEMITONE.get(degree, 0)) % 12
    return get_note_value(chord_data.get("root") or chord_data.get("text", ""))


def _is_minor_quality(text: str) -> bool:
    """Detect minor quality without false-positives on 'maj'."""
    if "dim" in text:
        return True
    if "m" not in text:
        return False
    # "mmaj7" has both 'm' and 'maj' — check if 'm' appears before 'maj'
    m_idx = text.index("m")
    if "maj" in text:
        maj_idx = text.index("maj")
        return m_idx < maj_idx
    return True


def _seventh_interval(text: str, is_dim: bool) -> int | None:
    """Return the seventh interval (semitones above root), or None."""
    if "maj7" in text or "mmaj7" in text:
        return 11
    if is_dim and "7" in text:
        return 9  # diminished 7th (double-flat 7th)
    if "7" in text or "9" in text or "11" in text or "13" in text:
        return 10 if _is_minor_quality(text) or "maj" not in text else 11
    return None


def _add_extensions(
    notes: list[int], root_val: int, text: str,
) -> None:
    """Append 6th/9th/11th/13th pitch classes based on chord text."""
    # 6th — add major 6th (+9)
    if "6" in text and "13" not in text:
        pc = (root_val + 9) % 12
        if pc not in notes:
            notes.append(pc)

    has_add = "add" in text

    # 9th (+2 mod 12)
    if "9" in text or (not has_add and ("11" in text or "13" in text)):
        pc = (root_val + 2) % 12
        if pc not in notes:
            notes.append(pc)

    # 11th (+5 mod 12) — for add11 or explicit 11
    if "11" in text:
        pc = (root_val + 5) % 12
        if pc not in notes:
            notes.append(pc)

    # 13th (+9 mod 12) — for add13 or explicit 13
    if "13" in text:
        pc = (root_val + 9) % 12
        if pc not in notes:
            notes.append(pc)


def get_chord_notes(chord_data: dict[str, Any], key: dict[str, str]) -> list[int]:
    """Pitch classes for the chord: root, 3rd, 5th, optional 7th, extensions."""
    root_val = get_chord_root_value(chord_data, key)
    notes = [root_val]
    text = str(chord_data.get("text", "")).lower()

    # Third
    is_dim = "dim" in text
    if _is_minor_quality(text):
        notes.append((root_val + 3) % 12)
    elif "sus4" in text:
        notes.append((root_val + 5) % 12)
    elif "sus2" in text:
        notes.append((root_val + 2) % 12)
    else:
        notes.append((root_val + 4) % 12)

    # Fifth
    if is_dim or "b5" in text:
        notes.append((root_val + 6) % 12)
    elif "aug" in text or "+" in text:
        notes.append((root_val + 8) % 12)
    else:
        notes.append((root_val + 7) % 12)

    # Seventh
    has_add = "add" in text
    seventh = _seventh_interval(text, is_dim)
    if seventh is not None and not has_add:
        notes.append((root_val + seventh) % 12)

    # Extensions (6th, 9th, 11th, 13th, add chords)
    _add_extensions(notes, root_val, text)

    return notes


def get_chord_midi_notes(
    chord_data: dict[str, Any],
    key: dict[str, str],
    *,
    voicing_style: str = "close",
    prev_midis: list[int] | None = None,
) -> list[int]:
    """Ascending MIDI note list starting at C3 (48 + root). Max 8 notes.

    *voicing_style*: ``"close"`` (default), ``"drop2"``, or ``"drop3"``.
    *prev_midis*: previous chord's MIDI notes for voice-leading optimization.
    """
    root_val = get_chord_root_value(chord_data, key)
    pcs = get_chord_notes(chord_data, key)

    if prev_midis is not None:
        return _voice_led_voicing(pcs, root_val, voicing_style, prev_midis)

    return _build_voicing(pcs, root_val, voicing_style)


def _build_voicing(pcs: list[int], root_val: int, style: str) -> list[int]:
    """Build ascending MIDI notes from pitch classes in the given voicing style."""
    base_root = 48 + root_val
    midis: list[int] = []
    previous = base_root - 1

    for pc in pcs:
        midi = base_root + ((pc - root_val + 12) % 12)
        while midi <= previous:
            midi += 12
        if midi not in midis:
            midis.append(midi)
            previous = midi

    midis = midis[:8]
    return _apply_drop(midis, style)


def _apply_drop(midis: list[int], style: str) -> list[int]:
    """Apply drop-2 or drop-3 voicing to a sorted note list."""
    if style == "drop2" and len(midis) >= 3:
        midis[len(midis) - 2] -= 12
        midis.sort()
    elif style == "drop3" and len(midis) >= 4:
        midis[len(midis) - 3] -= 12
        midis.sort()
    return midis


def _voice_led_voicing(
    pcs: list[int],
    root_val: int,
    style: str,
    prev_midis: list[int],
) -> list[int]:
    """Find the voicing that minimizes total semitone movement from *prev_midis*."""
    candidates = _generate_voicing_candidates(pcs, root_val, style)
    if not candidates:
        return _build_voicing(pcs, root_val, style)
    return min(candidates, key=lambda c: _voice_leading_cost(prev_midis, c))


def _generate_voicing_candidates(
    pcs: list[int], root_val: int, style: str,
) -> list[list[int]]:
    """Generate all reasonable inversions in the given voicing style."""
    candidates: list[list[int]] = []

    for rotation in range(len(pcs)):
        rotated = pcs[rotation:] + pcs[:rotation]
        voicing = _build_voicing_from_bass(rotated, style)
        candidates.append(voicing)

    # Octave-shifted variants.
    for v in list(candidates):
        up = [n + 12 for n in v]
        down = [n - 12 for n in v]
        if all(28 <= n <= 96 for n in up):
            candidates.append(up)
        if all(28 <= n <= 96 for n in down):
            candidates.append(down)

    return candidates


def _build_voicing_from_bass(ordered_pcs: list[int], style: str) -> list[int]:
    """Build MIDI notes where the first pitch class is the lowest voice."""
    bass_pc = ordered_pcs[0]
    base = 48 + bass_pc
    midis = [base]

    for pc in ordered_pcs[1:]:
        midi = base + ((pc - bass_pc + 12) % 12)
        while midi <= midis[-1]:
            midi += 12
        midis.append(midi)

    midis = midis[:8]
    return _apply_drop(midis, style)


def _voice_leading_cost(prev: list[int], next_: list[int]) -> int:
    """Total absolute semitone movement between two voicings."""
    if not prev or not next_:
        return 0
    if len(prev) == len(next_):
        return sum(abs(a - b) for a, b in zip(sorted(prev), sorted(next_)))
    shorter, longer = (prev, next_) if len(prev) <= len(next_) else (next_, prev)
    total = 0
    for note in shorter:
        closest = min(longer, key=lambda n: abs(n - note))
        total += abs(note - closest)
    return total


def get_chord_bass_value(chord_data: dict[str, Any], key: dict[str, str]) -> int:
    """Bass root pitch class. Handles slash chords (e.g. D/F#)."""
    m = _SLASH_BASS_RE.search(str(chord_data.get("text", "")))
    if m:
        return get_note_value(m.group(1))
    return get_chord_root_value(chord_data, key)


def get_bass_midi(chord_data: dict[str, Any], key: dict[str, str]) -> int:
    """Bass MIDI note from C2 (36 + bass_value), clamped to 28–52."""
    midi = 36 + get_chord_bass_value(chord_data, key)
    while midi > 52:
        midi -= 12
    while midi < 28:
        midi += 12
    return midi
