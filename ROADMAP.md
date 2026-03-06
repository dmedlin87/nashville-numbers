# ROADMAP

This file is the canonical project roadmap.

## Status

Current active work is the first music-lab transport slice from `NAM_MUSIC_EXPANSION_IDEA.md`: turn converted charts into a structured arrangement lane with groove presets, timeline playback, and reusable planning data for later live-input, NAM, and export work.

## Current Track

### In Progress

- Land the first arrangement planner and transport UI inside the existing embedded GUI.
- Keep the current converter, fretboard, and audio fallback behavior intact while exposing a stronger playback surface.
- Reuse the current audio stack before introducing separate NAM/live-input integration work.

### Just Landed

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
- Latest verified result during this track: `160 passed, 1 skipped`

## Next Steps

### Phase 1: Tighten the Music Lab Contract

- Add arrangement export primitives so the same planner can drive MIDI/stem hand-off workflows.
- Expand groove logic beyond fixed presets into more explicit pattern generation and variation controls.
- Keep the transport contract stable while deciding where live-input monitoring should attach.

Why this is next:
- It makes the current bar map useful even before NAM or live-input work starts.
- It preserves the low-risk foundation already built around GUI/runtime seams.

### Phase 2: Add Tone-Aware Input and Output Layers

- Add live-input experiments on top of the transport and fretboard targets.
- Explore NAM/IR insertion where believable source audio exists.
- Keep the transport planner independent from the eventual tone engine.

Why this matters:
- The hard part of the broader idea is not chart parsing; it is source realism, routing, and UX layering around playback.

### Explicitly Deferred

- Splitting the embedded frontend `_HTML` into separate assets.
- Full NAM integration and tone-browser workflows.
- Replacing `_DEFAULT_APP` usage across the whole module in one large change.
- Any large GUI asset split or framework migration while the transport contract is still moving.
