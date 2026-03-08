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


def get_chord_notes(chord_data: dict[str, Any], key: dict[str, str]) -> list[int]:
    """Pitch classes for the chord: root, 3rd, 5th, optional 7th."""
    root_val = get_chord_root_value(chord_data, key)
    notes = [root_val]
    text = str(chord_data.get("text", "")).lower()

    # Third
    if "m" in text and "maj" not in text:
        notes.append((root_val + 3) % 12)
    elif "dim" in text:
        notes.append((root_val + 3) % 12)
    elif "sus4" in text:
        notes.append((root_val + 5) % 12)
    elif "sus2" in text:
        notes.append((root_val + 2) % 12)
    else:
        notes.append((root_val + 4) % 12)

    # Fifth
    if "dim" in text or "b5" in text:
        notes.append((root_val + 6) % 12)
    elif "aug" in text or "+" in text:
        notes.append((root_val + 8) % 12)
    else:
        notes.append((root_val + 7) % 12)

    # Seventh
    if "maj7" in text:
        notes.append((root_val + 11) % 12)
    elif "7" in text:
        notes.append((root_val + 10) % 12)

    return notes


def get_chord_midi_notes(chord_data: dict[str, Any], key: dict[str, str]) -> list[int]:
    """Ascending MIDI note list starting at C3 (48 + root). Max 8 notes."""
    root_val = get_chord_root_value(chord_data, key)
    pcs = get_chord_notes(chord_data, key)
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

    return midis[:8]


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
