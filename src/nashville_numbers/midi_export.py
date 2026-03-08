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


def _time_sig_meta(numerator: int, denominator_power: int = 2) -> bytes:
    """Return a time signature meta-event (FF 58 04 nn dd cc bb).

    *denominator_power* encodes the denominator as a power of 2 (e.g. 2 = quarter note).
    """
    return b"\xFF\x58\x04" + bytes([numerator, denominator_power, 24, 8])


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


def _program_change(channel: int, program: int) -> bytes:
    """Return a MIDI Program Change message (C0-CF pp)."""
    return bytes([0xC0 | (channel & 0x0F), program & 0x7F])


# ---------------------------------------------------------------------------
# Stem track builder
# ---------------------------------------------------------------------------


def _build_stem_track(
    events: list[dict[str, Any]],
    bpm: int,
    *,
    channel: int,
    program: int | None,
) -> bytes:
    """Build a single MTrk from a list of sequence events for one stem."""
    abs_events: list[tuple[int, int, int, int, int]] = []

    for event in events:
        if event["kind"] == "note":
            midi = event["midi"]
            vel = event["velocity"]
            on_tick = _ms_to_ticks(event["delay_ms"], bpm)
            off_tick = _ms_to_ticks(event["delay_ms"] + event["duration_ms"], bpm)
            abs_events.append((on_tick, 1, channel, midi, vel))
            abs_events.append((off_tick, 0, channel, midi, 0))
        elif event["kind"] == "chord":
            midis = event["midis"]
            vel = event["velocity"]
            style = event.get("style", "block")
            strum_ms = event.get("strum_ms", 0)
            for i, midi in enumerate(midis):
                strum_offset = i * strum_ms if style == "strum" else 0
                on_tick = _ms_to_ticks(event["delay_ms"] + strum_offset, bpm)
                off_tick = _ms_to_ticks(
                    event["delay_ms"] + strum_offset + event["duration_ms"], bpm
                )
                abs_events.append((on_tick, 1, channel, midi, vel))
                abs_events.append((off_tick, 0, channel, midi, 0))

    abs_events.sort(key=lambda e: (e[0], e[1]))

    track_events: list[tuple[int, bytes]] = []

    if program is not None:
        track_events.append((0, _program_change(channel, program)))

    prev_tick = 0
    for abs_tick, order, ch, midi, vel in abs_events:
        delta = abs_tick - prev_tick
        if order == 1:
            track_events.append((delta, _note_on(ch, midi, vel)))
        else:
            track_events.append((delta, _note_off(ch, midi)))
        prev_tick = abs_tick

    track_events.append((0, _end_of_track()))
    return _track_chunk(track_events)


# ---------------------------------------------------------------------------
# High-level export API
# ---------------------------------------------------------------------------


def export_midi_bytes(
    plan: dict[str, Any],
    *,
    sequence: dict[str, Any] | None = None,
    include_count_in: bool = True,
) -> bytes:
    """Export a plan as Standard MIDI File bytes (Type 1, stem-separated).

    If *sequence* is ``None``, calls ``build_arrangement_sequence(plan)``
    internally.  Returns raw bytes suitable for writing to a ``.mid`` file.
    """
    if sequence is None:
        sequence = build_arrangement_sequence(plan)

    bpm = plan["tempo"]
    meter = plan.get("meter", 4)
    groove = plan.get("groove", {})
    ci_end_ms = _count_in_end_ms(plan)

    # --- Track 0: tempo + time signature ---
    tempo_track = _track_chunk([
        (0, _time_sig_meta(meter)),
        (0, _tempo_meta(bpm)),
        (0, _end_of_track()),
    ])

    # --- Partition events by stem ---
    chord_events: list[dict[str, Any]] = []
    bass_events: list[dict[str, Any]] = []
    countin_events: list[dict[str, Any]] = []
    drum_events: list[dict[str, Any]] = []

    for event in sequence["events"]:
        if not include_count_in and event["delay_ms"] < ci_end_ms:
            continue

        if event["channel"] == 9:
            if event["delay_ms"] < ci_end_ms:
                countin_events.append(event)
            else:
                drum_events.append(event)
        elif event["kind"] == "note" and event["channel"] == 0:
            if event["delay_ms"] < ci_end_ms:
                countin_events.append(event)
            else:
                chord_events.append(event)
        elif event["kind"] == "chord":
            chord_events.append(event)
        elif event["channel"] == 1:
            bass_events.append(event)

    tracks = [tempo_track]

    # --- Track 1: Chords ---
    chord_program = groove.get("chord_program", 0)
    tracks.append(_build_stem_track(chord_events, bpm, channel=0, program=chord_program))

    # --- Track 2: Bass ---
    bass_program = groove.get("bass_program", 33)
    tracks.append(_build_stem_track(bass_events, bpm, channel=1, program=bass_program))

    # --- Track 3: Count-in (GM percussion, channel 9) ---
    if countin_events:
        tracks.append(_build_stem_track(countin_events, bpm, channel=9, program=None))

    # --- Track 4: Drums (GM percussion, channel 9) ---
    if drum_events:
        tracks.append(_build_stem_track(drum_events, bpm, channel=9, program=None))

    # --- Header ---
    num_tracks = len(tracks)
    header = b"MThd" + struct.pack(">IhhH", 6, 1, num_tracks, _TICKS_PER_BEAT)

    return header + b"".join(tracks)


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
