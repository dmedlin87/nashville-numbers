"""Plan-to-event-list conversion — Python port of JS buildArrangementSequence."""

from __future__ import annotations

import random
from typing import Any

from .voicing import get_bass_midi, get_chord_midi_notes, slot_to_chord_data


def build_arrangement_sequence(plan: dict[str, Any]) -> dict[str, Any]:
    """Convert a plan dict into a flat event list for AudioService.play_sequence.

    Returns ``{"events": [...], "highlights": [...], "total_ms": int}``.
    """
    groove = plan["groove"]
    beat_ms = 60_000.0 / plan["tempo"]
    events: list[dict[str, Any]] = []
    highlights: list[dict[str, Any]] = []

    # Count-in clicks.
    events.extend(_build_count_in_events(plan["count_in_beats"], beat_ms))

    cursor_beats = float(plan["count_in_beats"])

    for section_index, section in enumerate(plan["sections"]):
        for bar_index, bar in enumerate(section["bars"]):
            bar_start_beats = cursor_beats
            for slot_index, slot in enumerate(bar["slots"]):
                chord_data = slot_to_chord_data(slot)
                key = {"tonic": slot["key"]["tonic"], "mode": slot["key"]["mode"]}
                midis = get_chord_midi_notes(chord_data, key)
                if not midis:
                    continue

                base_velocity = 82 if groove["id"] == "lantern" else 96
                events.extend(
                    _build_chord_events_from_pattern(
                        slot, midis, groove, bar_start_beats, beat_ms, base_velocity,
                    )
                )

                slot_start_ms = round((bar_start_beats + slot["beat_start"]) * beat_ms)
                slot_duration_ms = max(
                    180,
                    round(slot["beat_duration"] * beat_ms * groove["gate"]),
                )

                if plan.get("bass_enabled", True):
                    events.extend(
                        _build_bass_events(slot, chord_data, key, groove, slot_start_ms, beat_ms)
                    )

                slot_key = f"{section_index}-{bar_index}-{slot_index}"
                highlights.append({
                    "key": slot_key,
                    "delay_ms": slot_start_ms,
                    "duration_ms": max(220, slot_duration_ms),
                })

            cursor_beats += bar["beats"]

    total_ms = round(cursor_beats * beat_ms + 240)

    count_in_end_ms = round(float(plan["count_in_beats"]) * beat_ms)
    seed = plan.get("expression_seed", 42)
    _apply_expression(events, groove, beat_ms, count_in_end_ms, seed)

    return {"events": events, "highlights": highlights, "total_ms": total_ms}


def _build_count_in_events(count_in_beats: int, beat_ms: float) -> list[dict[str, Any]]:
    """Generate metronome click events for the count-in."""
    events: list[dict[str, Any]] = []
    for beat in range(count_in_beats):
        is_last = beat == count_in_beats - 1
        events.append({
            "kind": "note",
            "delay_ms": round(beat * beat_ms),
            "duration_ms": 140,
            "velocity": 118 if is_last else 92,
            "channel": 0,
            "midi": 84 if is_last else 79,
        })
    return events


def _build_chord_events_from_pattern(
    slot: dict[str, Any],
    midis: list[int],
    groove: dict[str, Any],
    bar_start_beats: float,
    beat_ms: float,
    base_velocity: int,
) -> list[dict[str, Any]]:
    """Generate chord events from the groove's ``chord_pattern`` descriptors."""
    chord_pattern = groove.get("chord_pattern", [{"beat": 0.0, "velocity_scale": 1.0}])
    events: list[dict[str, Any]] = []

    for hit in chord_pattern:
        beat_offset = hit.get("beat", 0.0)
        if beat_offset >= slot["beat_duration"]:
            continue

        start_ms = round((bar_start_beats + slot["beat_start"] + beat_offset) * beat_ms)
        remaining_beats = slot["beat_duration"] - beat_offset
        duration_ms = max(180, round(remaining_beats * beat_ms * groove["gate"]))

        vel_scale = hit.get("velocity_scale", 1.0)
        velocity = max(1, min(127, round(base_velocity * vel_scale)))

        events.append({
            "kind": "chord",
            "delay_ms": start_ms,
            "duration_ms": duration_ms,
            "velocity": velocity,
            "channel": 0,
            "midis": midis,
            "style": groove["chord_style"],
            "strum_ms": groove["strum_ms"],
        })

    return events


def _build_bass_events(
    slot: dict[str, Any],
    chord_data: dict[str, Any],
    key: dict[str, str],
    groove: dict[str, Any],
    start_ms: int,
    beat_ms: float,
) -> list[dict[str, Any]]:
    """Generate bass events for a slot per the groove's bass_pattern."""
    # If the groove has explicit bass_hits, use those.
    if "bass_hits" in groove:
        return _build_bass_events_from_hits(
            slot, chord_data, key, groove["bass_hits"], start_ms, beat_ms
        )

    # Fall back to string-enum interpretation.
    bass_pattern = groove.get("bass_pattern", "slot-roots")
    bass_midi = get_bass_midi(chord_data, key)
    short_ms = max(140, round(min(slot["beat_duration"] * beat_ms * 0.48, 340)))
    events: list[dict[str, Any]] = []

    if bass_pattern in ("bar-root", "half-time") and slot["beat_start"] != 0:
        return events

    events.append({
        "kind": "note",
        "delay_ms": start_ms,
        "duration_ms": short_ms,
        "velocity": 86,
        "channel": 1,
        "midi": bass_midi,
    })

    if bass_pattern == "downbeat-octave" and slot["beat_duration"] >= 2:
        events.append({
            "kind": "note",
            "delay_ms": start_ms + round(beat_ms * min(2, slot["beat_duration"] / 2)),
            "duration_ms": short_ms,
            "velocity": 78,
            "channel": 1,
            "midi": min(76, bass_midi + 12),
        })

    return events


def _build_bass_events_from_hits(
    slot: dict[str, Any],
    chord_data: dict[str, Any],
    key: dict[str, str],
    bass_hits: list[dict[str, Any]],
    start_ms: int,
    beat_ms: float,
) -> list[dict[str, Any]]:
    """Generate bass events from explicit ``bass_hits`` descriptors."""
    bass_midi = get_bass_midi(chord_data, key)
    events: list[dict[str, Any]] = []
    short_ms = max(140, round(min(slot["beat_duration"] * beat_ms * 0.48, 340)))

    for hit in bass_hits:
        # Skip if slot doesn't start on beat 0 and hit requires it.
        beat = hit.get("beat", 0.0)
        if beat == 0.0 and slot["beat_start"] != 0 and hit.get("bar_downbeat_only", False):
            continue

        # Skip if the slot is too short for this hit.
        min_beats = hit.get("min_slot_beats", 0)
        if slot["beat_duration"] < min_beats:
            continue

        # Use beat as fraction of slot duration when beat_fraction is set.
        if "beat_fraction" in hit:
            delay = start_ms + round(hit["beat_fraction"] * slot["beat_duration"] * beat_ms)
        else:
            delay = start_ms + round(beat * beat_ms)

        octave_offset = hit.get("octave_offset", 0)
        midi = bass_midi + 12 * octave_offset
        midi = min(76, max(28, midi))

        events.append({
            "kind": "note",
            "delay_ms": delay,
            "duration_ms": short_ms,
            "velocity": hit.get("velocity", 86),
            "channel": 1,
            "midi": midi,
        })

    return events


def _apply_expression(
    events: list[dict[str, Any]],
    groove: dict[str, Any],
    beat_ms: float,
    count_in_end_ms: float,
    seed: int = 42,
) -> None:
    """Apply swing, humanize, and velocity variance to the event list in place.

    Only modifies events whose ``delay_ms`` is at or after *count_in_end_ms*.
    """
    swing = groove.get("swing", 0.0)
    humanize_ms_range = groove.get("humanize_ms", 0)
    vel_var = groove.get("velocity_variance", 0)

    if swing == 0.0 and humanize_ms_range == 0 and vel_var == 0:
        return

    rng = random.Random(seed)

    for event in events:
        delay = event["delay_ms"]
        if delay < count_in_end_ms:
            continue

        # Swing: shift off-beat eighth notes forward.
        if swing > 0.0:
            beat_position = delay / beat_ms
            frac = beat_position % 1.0
            if 0.45 <= frac <= 0.55:
                event["delay_ms"] = round(delay + swing * (beat_ms / 3.0))

        # Humanize: random timing jitter.
        if humanize_ms_range > 0:
            jitter = rng.uniform(-humanize_ms_range, humanize_ms_range)
            event["delay_ms"] = max(0, round(event["delay_ms"] + jitter))

        # Velocity variance: random offset clamped to [1, 127].
        if vel_var > 0 and "velocity" in event:
            offset = rng.randint(-vel_var, vel_var)
            event["velocity"] = max(1, min(127, event["velocity"] + offset))

