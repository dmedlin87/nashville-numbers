"""Progression planning helpers for the music-lab transport."""

from __future__ import annotations

from typing import Any

from .converter import _convert_chords_to_nns, _convert_nns_to_chords, _extract_progression
from .key_inference import infer_keys, infer_sections
from .parser import parse_input, tokenize_progression

GROOVE_PRESETS: dict[str, dict[str, Any]] = {
    "anthem": {
        "id": "anthem",
        "name": "Anthem Strum",
        "description": "Wide downbeat strums with bass anchors.",
        "chord_style": "strum",
        "strum_ms": 24,
        "gate": 0.86,
        "bass_pattern": "downbeat-octave",
        "chord_pattern": [{"beat": 0.0, "velocity_scale": 1.0}],
        "bass_hits": [
            {"beat": 0.0, "velocity": 86, "octave_offset": 0},
            {"beat_fraction": 0.5, "velocity": 78, "octave_offset": 1, "min_slot_beats": 2},
        ],
        "swing": 0.0,
        "humanize_ms": 0,
        "velocity_variance": 0,
    },
    "pulse": {
        "id": "pulse",
        "name": "Pulse Grid",
        "description": "Tight block hits that keep the chart moving.",
        "chord_style": "block",
        "strum_ms": 0,
        "gate": 0.66,
        "bass_pattern": "slot-roots",
        "chord_pattern": [{"beat": 0.0, "velocity_scale": 1.0}],
        "bass_hits": [
            {"beat": 0.0, "velocity": 86, "octave_offset": 0},
        ],
        "swing": 0.0,
        "humanize_ms": 0,
        "velocity_variance": 0,
    },
    "lantern": {
        "id": "lantern",
        "name": "Lantern Pick",
        "description": "Short picked stabs with a lighter low-end bed.",
        "chord_style": "strum",
        "strum_ms": 16,
        "gate": 0.52,
        "bass_pattern": "half-time",
        "chord_pattern": [{"beat": 0.0, "velocity_scale": 1.0}],
        "bass_hits": [
            {"beat": 0.0, "velocity": 86, "octave_offset": 0, "bar_downbeat_only": True},
        ],
        "swing": 0.0,
        "humanize_ms": 0,
        "velocity_variance": 0,
    },
    "pads": {
        "id": "pads",
        "name": "Cinema Pads",
        "description": "Held chords for sketching larger arrangement ideas.",
        "chord_style": "block",
        "strum_ms": 0,
        "gate": 1.0,
        "bass_pattern": "bar-root",
        "chord_pattern": [{"beat": 0.0, "velocity_scale": 1.0}],
        "bass_hits": [
            {"beat": 0.0, "velocity": 86, "octave_offset": 0, "bar_downbeat_only": True},
        ],
        "swing": 0.0,
        "humanize_ms": 0,
        "velocity_variance": 0,
    },
}

# Required fields for a valid groove dict.
_GROOVE_REQUIRED = {"id", "chord_style", "strum_ms", "gate", "bass_pattern"}


def resolve_groove(groove: str | dict[str, Any]) -> dict[str, Any]:
    """Resolve a groove from its preset ID or validate a custom groove dict.

    Returns a normalized groove dict with all required fields present.
    """
    if isinstance(groove, str):
        key = groove.strip().lower() or "anthem"
        if key not in GROOVE_PRESETS:
            raise ValueError(f"Unknown groove '{groove}'")
        return dict(GROOVE_PRESETS[key])

    if not isinstance(groove, dict):
        raise TypeError(f"groove must be a str or dict, got {type(groove).__name__}")

    missing = _GROOVE_REQUIRED - set(groove)
    if missing:
        raise ValueError(f"Custom groove missing required fields: {sorted(missing)}")

    return dict(groove)


def build_progression_plan(
    input_text: str,
    *,
    tempo: int = 96,
    meter: int = 4,
    groove: str = "anthem",
    count_in_beats: int = 4,
    bass_enabled: bool = True,
) -> dict[str, Any]:
    """Resolve input text into arrangement sections, bars, and timing metadata."""
    if not input_text.strip():
        raise ValueError("Empty input")

    groove_key = groove.strip().lower() or "anthem"
    if groove_key not in GROOVE_PRESETS:
        raise ValueError(f"Unknown groove '{groove}'")

    parsed = parse_input(input_text)
    progression = _extract_progression(parsed.text)
    if not progression:
        raise ValueError("Empty input")

    resolved_sections = _resolve_sections(parsed, progression)
    sections_payload: list[dict[str, Any]] = []
    total_bars = 0
    total_slots = 0
    total_beats = 0.0
    primary_key: dict[str, str] | None = None
    key_count = 0

    for index, section in enumerate(resolved_sections, start=1):
        bars, section_beats = _build_bars(
            section["chords"],
            section["nns"],
            meter=meter,
            key=section["key"],
        )
        total_bars += len(bars)
        total_slots += sum(len(bar["slots"]) for bar in bars)
        total_beats += section_beats
        key_count += 1 if section["key"] else 0
        if primary_key is None:
            primary_key = dict(section["key"])

        sections_payload.append(
            {
                "index": index,
                "label": section["label"],
                "analysis": section["analysis"],
                "key": dict(section["key"]),
                "preview": " | ".join(bar["preview"] for bar in bars),
                "bars": bars,
            }
        )

    resolved_via = sections_payload[0]["analysis"] if len(sections_payload) == 1 else "section_inference"
    if primary_key is None:
        primary_key = {"tonic": "C", "mode": "Major"}

    total_seconds = round(((count_in_beats + total_beats) * 60.0) / float(tempo), 2)
    return {
        "input_mode": parsed.mode,
        "analysis": {
            "resolved_via": resolved_via,
            "key_changes": max(0, key_count - 1),
        },
        "tempo": tempo,
        "meter": meter,
        "meter_label": _format_meter_label(meter),
        "count_in_beats": count_in_beats,
        "bass_enabled": bool(bass_enabled),
        "groove": dict(GROOVE_PRESETS[groove_key]),
        "resolved_key": primary_key,
        "summary": {
            "section_count": len(sections_payload),
            "bar_count": total_bars,
            "slot_count": total_slots,
            "loop_beats": round(total_beats, 3),
            "loop_seconds": total_seconds,
        },
        "sections": sections_payload,
    }


def _resolve_sections(parsed: Any, progression: str) -> list[dict[str, Any]]:
    if parsed.mode == "nns_to_chords":
        if not parsed.key_tonic:
            raise ValueError("Key: REQUIRED")
        key = {"tonic": parsed.key_tonic, "mode": parsed.key_mode or "Major"}
        return [
            {
                "label": "Main Loop",
                "analysis": "explicit_key",
                "key": key,
                "chords": _convert_nns_to_chords(progression, key["tonic"], key["mode"]),
                "nns": progression,
            }
        ]

    if parsed.key_tonic:
        key = {"tonic": parsed.key_tonic, "mode": parsed.key_mode or "Major"}
        return [
            {
                "label": "Main Loop",
                "analysis": "explicit_key",
                "key": key,
                "chords": progression,
                "nns": _convert_chords_to_nns(progression, key["tonic"], key["mode"]),
            }
        ]

    inferred = infer_sections(progression)
    if len(inferred) <= 1:
        choice = infer_keys(progression, max_keys=1)[0]
        return [
            {
                "label": "Main Loop",
                "analysis": "best_guess",
                "key": {"tonic": choice.tonic, "mode": choice.mode},
                "chords": progression,
                "nns": _convert_chords_to_nns(progression, choice.tonic, choice.mode),
            }
        ]

    resolved_sections: list[dict[str, Any]] = []
    for index, (section_text, choice) in enumerate(inferred, start=1):
        resolved_sections.append(
            {
                "label": f"Section {index}",
                "analysis": "section_inference",
                "key": {"tonic": choice.tonic, "mode": choice.mode},
                "chords": section_text,
                "nns": _convert_chords_to_nns(section_text, choice.tonic, choice.mode),
            }
        )
    return resolved_sections


def _build_bars(
    chord_progression: str,
    nns_progression: str,
    *,
    meter: int,
    key: dict[str, str],
) -> tuple[list[dict[str, Any]], float]:
    chord_bars = _bars_from_progression(chord_progression)
    nns_bars = _bars_from_progression(nns_progression)
    bars: list[dict[str, Any]] = []
    total_beats = 0.0

    for bar_index, chord_tokens in enumerate(chord_bars, start=1):
        if not chord_tokens:
            continue
        bar_nns = nns_bars[bar_index - 1] if bar_index - 1 < len(nns_bars) else []
        aligned_nns = bar_nns if len(bar_nns) == len(chord_tokens) else [None] * len(chord_tokens)
        slots = _build_slots(chord_tokens, aligned_nns, meter=meter, key=key)
        bars.append(
            {
                "index": bar_index,
                "label": f"Bar {bar_index}",
                "beats": meter,
                "preview": "  ".join(chord_tokens),
                "slots": slots,
            }
        )
        total_beats += meter

    return bars, total_beats


def _build_slots(
    chord_tokens: list[str],
    nns_tokens: list[str | None],
    *,
    meter: int,
    key: dict[str, str],
) -> list[dict[str, Any]]:
    slot_count = len(chord_tokens)
    step = float(meter) / float(slot_count)
    slots: list[dict[str, Any]] = []

    for slot_index, chord in enumerate(chord_tokens, start=1):
        beat_start = round((slot_index - 1) * step, 4)
        next_start = float(meter) if slot_index == slot_count else round(slot_index * step, 4)
        beat_duration = round(next_start - beat_start, 4)
        slots.append(
            {
                "index": slot_index,
                "label": chord,
                "chord": chord,
                "nns": nns_tokens[slot_index - 1] if slot_index - 1 < len(nns_tokens) else None,
                "beat_start": beat_start,
                "beat_duration": beat_duration,
                "key": dict(key),
            }
        )

    return slots


def _bars_from_progression(text: str) -> list[list[str]]:
    if "|" in text:
        bars = [_musical_tokens(chunk) for chunk in text.split("|")]
        filtered = [bar for bar in bars if bar]
        if filtered:
            return filtered

    tokens = _musical_tokens(text)
    return [[token] for token in tokens]


def _musical_tokens(text: str) -> list[str]:
    return [
        token.text.strip()
        for token in tokenize_progression(text)
        if token.kind in {"chord", "nns"} and token.text.strip()
    ]


def _format_meter_label(meter: int) -> str:
    if meter == 6:
        return "6/8"
    return f"{meter}/4"
