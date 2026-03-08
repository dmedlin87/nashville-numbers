"""Minimal Standard MIDI File writer — zero external dependencies."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .sequence import build_arrangement_sequence

# Default resolution: 480 ticks per quarter note (standard).
_TICKS_PER_BEAT = 480


# ---------------------------------------------------------------------------
# Low-level SMF helpers
# ---------------------------------------------------------------------------


def _vlq(value: int) -> bytes:
    """Encode *value* as a MIDI variable-length quantity."""
    if value < 0:
        raise ValueError("VLQ value must be non-negative")
    buf = [value & 0x7F]
    value >>= 7
    while value:
        buf.append((value & 0x7F) | 0x80)
        value >>= 7
    buf.reverse()
    return bytes(buf)


def _tempo_meta(bpm: int) -> bytes:
    """Return a tempo meta-event (FF 51 03 tt tt tt)."""
    uspqn = round(60_000_000 / bpm)
    return b"\xFF\x51\x03" + struct.pack(">I", uspqn)[1:]


def _end_of_track() -> bytes:
    """Return an end-of-track meta-event (FF 2F 00)."""
    return b"\xFF\x2F\x00"


def _track_chunk(raw_events: list[tuple[int, bytes]]) -> bytes:
    """Build an MTrk chunk from ``(delta_ticks, raw_midi_bytes)`` pairs."""
    body = bytearray()
    for delta, data in raw_events:
        body.extend(_vlq(delta))
        body.extend(data)
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def _ms_to_ticks(ms: float, bpm: int) -> int:
    """Convert milliseconds to MIDI ticks at the given tempo."""
    ticks_per_ms = (_TICKS_PER_BEAT * bpm) / 60_000.0
    return round(ms * ticks_per_ms)


def _note_on(channel: int, midi: int, velocity: int) -> bytes:
    return bytes([0x90 | (channel & 0x0F), midi & 0x7F, velocity & 0x7F])


def _note_off(channel: int, midi: int) -> bytes:
    return bytes([0x80 | (channel & 0x0F), midi & 0x7F, 0])


# ---------------------------------------------------------------------------
# High-level export API
# ---------------------------------------------------------------------------


def export_midi_bytes(
    plan: dict[str, Any],
    *,
    sequence: dict[str, Any] | None = None,
    include_count_in: bool = True,
) -> bytes:
    """Export a plan as Standard MIDI File bytes (Type 1, 2 tracks).

    If *sequence* is ``None``, calls ``build_arrangement_sequence(plan)``
    internally.  Returns raw bytes suitable for writing to a ``.mid`` file.
    """
    if sequence is None:
        sequence = build_arrangement_sequence(plan)

    bpm = plan["tempo"]

    # --- Track 0: tempo ---
    tempo_track = _track_chunk([
        (0, _tempo_meta(bpm)),
        (0, _end_of_track()),
    ])

    # --- Track 1: notes ---
    # Collect absolute-tick (on/off, channel, midi, velocity) tuples,
    # then sort by tick and convert to delta-time stream.
    abs_events: list[tuple[int, int, int, int, int]] = []
    # Each tuple: (abs_tick, order, channel, midi, velocity)
    # order: 0 = note-off, 1 = note-on (so note-offs sort before note-ons at same tick)

    count_in_beats = plan.get("count_in_beats", 4)
    order_counter = 0

    for event in sequence["events"]:
        # Optionally skip count-in.
        if not include_count_in and event["delay_ms"] < _count_in_end_ms(plan):
            continue

        if event["kind"] == "note":
            midi = event["midi"]
            vel = event["velocity"]
            ch = event["channel"]
            on_tick = _ms_to_ticks(event["delay_ms"], bpm)
            off_tick = _ms_to_ticks(event["delay_ms"] + event["duration_ms"], bpm)
            abs_events.append((on_tick, 1, ch, midi, vel))
            abs_events.append((off_tick, 0, ch, midi, 0))
            order_counter += 2

        elif event["kind"] == "chord":
            midis = event["midis"]
            vel = event["velocity"]
            ch = event["channel"]
            style = event.get("style", "block")
            strum_ms = event.get("strum_ms", 0)

            for i, midi in enumerate(midis):
                strum_offset = i * strum_ms if style == "strum" else 0
                on_tick = _ms_to_ticks(event["delay_ms"] + strum_offset, bpm)
                off_tick = _ms_to_ticks(
                    event["delay_ms"] + strum_offset + event["duration_ms"], bpm
                )
                abs_events.append((on_tick, 1, ch, midi, vel))
                abs_events.append((off_tick, 0, ch, midi, 0))

    # Sort: by tick, then note-off before note-on at same tick (order field).
    abs_events.sort(key=lambda e: (e[0], e[1]))

    # Convert to delta-tick stream.
    note_track_events: list[tuple[int, bytes]] = []
    prev_tick = 0
    for abs_tick, order, ch, midi, vel in abs_events:
        delta = abs_tick - prev_tick
        if order == 1:
            note_track_events.append((delta, _note_on(ch, midi, vel)))
        else:
            note_track_events.append((delta, _note_off(ch, midi)))
        prev_tick = abs_tick

    note_track_events.append((0, _end_of_track()))
    note_track = _track_chunk(note_track_events)

    # --- Header ---
    header = b"MThd" + struct.pack(">IhhH", 6, 1, 2, _TICKS_PER_BEAT)

    return header + tempo_track + note_track


def export_midi_file(
    plan: dict[str, Any],
    path: str | Path,
    *,
    sequence: dict[str, Any] | None = None,
    include_count_in: bool = True,
) -> Path:
    """Write a MIDI file to *path*. Returns the ``Path`` written."""
    p = Path(path)
    p.write_bytes(export_midi_bytes(
        plan, sequence=sequence, include_count_in=include_count_in,
    ))
    return p


def _count_in_end_ms(plan: dict[str, Any]) -> float:
    """Millisecond position where the count-in ends."""
    beat_ms = 60_000.0 / plan["tempo"]
    return plan.get("count_in_beats", 4) * beat_ms
