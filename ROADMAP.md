# ROADMAP

This file is the canonical project roadmap.

## Status

Current active work: Phase 1 of the Music Lab expansion is complete. The arrangement planner now drives a full MIDI export pipeline with Python-side chord voicing, sequence generation, and a zero-dependency MIDI file writer. Groove presets carry explicit pattern fields for future variation work.

## Current Track

### In Progress

- Stabilize Phase 1 and identify Phase 2 entry points for tone-aware layers.

### Just Landed

- Ported JS chord voicing to Python (`voicing.py`): note value lookup, chord/NNS root resolution, pitch-class derivation, MIDI voicing (C3 base), slash-chord bass voicing.
- Added Python-side plan-to-event-list conversion (`sequence.py`): count-in, chord, and bass events matching the existing `AudioService.play_sequence` contract.
- Built a zero-dependency Standard MIDI File writer (`midi_export.py`): Type 1 SMF with tempo track and note track, ms-to-tick conversion, strum/block voicing in MIDI output.
- Expanded groove presets with explicit `bass_hits`, `chord_pattern`, `swing`, `humanize_ms`, and `velocity_variance` fields. Added `resolve_groove()` for custom groove validation.
- Wired `POST /arrangement/export-midi` endpoint and GUI Export MIDI button that triggers a browser download.
- Added a progression planner module for sections, bars, harmonic slots, and timing metadata.
- Added sequence playback support so the GUI can queue an entire loop through the existing audio service.
- Expanded the embedded GUI with a new Music Lab panel, groove presets, timeline interaction, and transport controls.

### Completed

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
- Latest verified result during this track: `289 passed, 1 skipped`

## Next Steps

### Phase 2: Add Tone-Aware Input and Output Layers

- Add live-input experiments on top of the transport and fretboard targets.
- Explore NAM/IR insertion where believable source audio exists.
- Keep the transport planner independent from the eventual tone engine.
- Apply swing/humanize/velocity variance in the sequence builder.
- Add pattern generation algorithms for groove creation.
- Expand MIDI export with stem-separated tracks and GM program changes.

Why this matters:
- The hard part of the broader idea is not chart parsing; it is source realism, routing, and UX layering around playback.
- The Phase 1 export primitives and enriched groove model now provide a stable foundation.

### Explicitly Deferred

- Splitting the embedded frontend `_HTML` into separate assets.
- Full NAM integration and tone-browser workflows.
- Replacing `_DEFAULT_APP` usage across the whole module in one large change.
- Any large GUI asset split or framework migration while the transport contract is still moving.
