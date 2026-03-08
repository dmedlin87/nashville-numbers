# ROADMAP

This file is the canonical project roadmap.

## Status

Current active work: Phase 2 of the Music Lab expansion is complete. The sequence builder now consumes `chord_pattern` for multi-hit grooves and applies swing, humanize, and velocity variance via a deterministic post-processing pass. MIDI export produces stem-separated tracks with GM program changes. All four groove presets carry musically tuned expression values.

## Current Track

### In Progress

- Identify Phase 3 entry points for live-input and tone-aware layers.

### Just Landed

- Wired `chord_pattern` consumption in the sequence builder (`sequence.py`): the groove's `chord_pattern` list now drives multi-hit chord events per slot with beat offsets and velocity scaling.
- Added `_apply_expression` post-processing pass (`sequence.py`): applies swing (off-beat eighth shift), humanize (deterministic RNG timing jitter), and velocity variance to all non-count-in events. Controllable via `expression_seed` for reproducibility.
- Refactored MIDI export to stem-separated tracks (`midi_export.py`): Type 1 SMF now outputs 3-4 tracks (tempo, chord stem, bass stem, optional count-in on GM percussion channel 9) with program change events and time signature meta-events.
- Added `chord_program` and `bass_program` fields to all groove presets for GM instrument assignment.
- Activated non-zero expression values across groove presets: anthem (humanize 8ms, variance 6), pulse (humanize 4ms, variance 4, 4-hit chord pattern), lantern (swing 0.3, humanize 6ms, variance 8, 2-hit pattern), pads (unchanged, clean baseline).

### Completed

- Ported JS chord voicing to Python (`voicing.py`): note value lookup, chord/NNS root resolution, pitch-class derivation, MIDI voicing (C3 base), slash-chord bass voicing.
- Added Python-side plan-to-event-list conversion (`sequence.py`): count-in, chord, and bass events matching the existing `AudioService.play_sequence` contract.
- Built a zero-dependency Standard MIDI File writer (`midi_export.py`): Type 1 SMF with tempo track and note track, ms-to-tick conversion, strum/block voicing in MIDI output.
- Expanded groove presets with explicit `bass_hits`, `chord_pattern`, `swing`, `humanize_ms`, and `velocity_variance` fields. Added `resolve_groove()` for custom groove validation.
- Wired `POST /arrangement/export-midi` endpoint and GUI Export MIDI button that triggers a browser download.
- Added a progression planner module for sections, bars, harmonic slots, and timing metadata.
- Added sequence playback support so the GUI can queue an entire loop through the existing audio service.
- Expanded the embedded GUI with a new Music Lab panel, groove presets, timeline interaction, and transport controls.
- Added direct characterization tests for `AudioService` orchestration in `tests/test_audio_service.py`.
- Extracted HTTP handler construction into `src/nashville_numbers/gui_http.py`.
- Moved mutable GUI runtime-install state behind `GuiApp`.
- Moved GUI server/bootstrap lifecycle behind `GuiApp`.
- Removed eager GUI handler construction at import time and made handler creation lazy/cached through `GuiApp`.
- Moved GUI startup side effects behind app methods:
  - HTTP server creation
  - thread creation
  - timer/event creation
  - `webview` import
  - browser open fallback
- Retargeted GUI startup tests to patch `GuiApp` methods instead of module globals.

### Current Safety Baseline

- Worktree-local test command: `PYTHONPATH=src python -m pytest -q`
- Latest verified result during this track: `313 passed, 1 skipped`

## Next Steps

### Phase 3: Live Input and Tone Exploration

- Add live-input experiments on top of the transport and fretboard targets.
- Explore NAM/IR insertion where believable source audio exists.
- Keep the transport planner independent from the eventual tone engine.
- Add pattern generation algorithms for algorithmic groove creation.
- Explore extended chord voicings (9ths, 11ths, 13ths) and voice leading.

Why this matters:
- The hard part of the broader idea is not chart parsing; it is source realism, routing, and UX layering around playback.
- The Phase 2 expression and stem-export capabilities now make the MIDI output directly useful in DAWs.

### Explicitly Deferred

- Splitting the embedded frontend `_HTML` into separate assets.
- Full NAM integration and tone-browser workflows.
- Replacing `_DEFAULT_APP` usage across the whole module in one large change.
- Any large GUI asset split or framework migration while the transport contract is still moving.
