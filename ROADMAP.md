# ROADMAP

This file is the canonical project roadmap.

## Status

Current active work: Phase 4 first batch is complete. All 9 groove presets are exposed in the GUI, voicing style and voice leading controls are wired end-to-end (GUI → HTTP → planner → sequence), and drum pattern support generates a percussion track in both the event list and MIDI export.

## Current Track

### In Progress

- Identify Phase 4 second-batch entry points: live-input experiments, NAM/IR exploration, per-channel program changes.

### Just Landed

- Synced all 9 groove presets to the front-end JS (`gui.py`): waltz, shuffle, funk, reggae, and ballad now appear in the groove picker grid alongside anthem, pulse, lantern, and pads.
- Added voicing style control (`gui.py`): `<select id="labVoicingStyle">` with Close, Drop-2, and Drop-3 options.
- Added voice leading toggle (`gui.py`): checkbox that minimizes note movement between consecutive chords.
- Wired `voicing_style` and `voice_leading` through HTTP endpoints (`gui_http.py`): both `POST /arrangement/plan` and `POST /arrangement/export-midi` now extract, validate, and pass these parameters to the planner.
- Added `drum_pattern` field to all 9 groove presets (`music_lab.py`): each preset defines per-beat GM percussion hits (kick, snare, hi-hat, ride, etc.). Pads and ballad use empty patterns for clean, percussion-free output.
- Added drum event generation (`sequence.py`): `_build_drum_events` emits `kind: "note"` events on channel 9 from the groove's drum pattern, one cycle per bar. Expression (humanize, velocity variance, swing) applies to drum events.
- Added drum track to MIDI export (`midi_export.py`): channel-9 drum events are partitioned into a separate track, distinct from the count-in track. Type 1 SMF now supports up to 5 tracks (tempo, chords, bass, count-in, drums).

### Completed

- Extended chord voicings (`voicing.py`): 6th, 9th, 11th, 13th, add9/add11/add13, maj9/maj11/maj13, min9/min11/min13 now produce correct pitch classes and MIDI notes. Fixed dim7 voicing bug (+9 instead of +10). Fixed mmaj7 minor-quality detection.
- Five new groove presets (`music_lab.py`): waltz (3/4 feel, 3 chord hits), shuffle (swing 0.5, octave bass), funk (syncopated 5-hit staccato), reggae (all-offbeat skank), ballad (wide sustained strum, GM harp).
- Arpeggio pattern support (`sequence.py`): grooves can define `arp_pattern` with `note_indices`, `step_beats`, `gate`, and `velocity_curve`. Arp events emit individual `kind: "note"` events on channel 0, cycling through chord tones. Works with existing MIDI export without changes.
- Walking bass (`sequence.py`): `bass_pattern: "walking"` generates 4-note walks per slot (root → 3rd → 5th → octave root) from chord pitch classes, all clamped to bass range 28–52.
- Voicing styles (`voicing.py`): `get_chord_midi_notes` accepts `voicing_style` param — `"close"` (default), `"drop2"` (2nd-highest note drops an octave), `"drop3"` (3rd-highest drops). Backwards compatible.
- Voice leading optimizer (`voicing.py`): `get_chord_midi_notes` accepts `prev_midis` for voice-leading. Generates all inversions × octave shifts, picks the voicing with minimum total semitone movement from the previous chord.
- Wired voice leading into the sequence builder (`sequence.py`): `build_arrangement_sequence` reads `voicing_style` and `voice_leading` from the plan dict, tracks `prev_midis` across slots.
- Plan parameters (`music_lab.py`): `build_progression_plan` accepts `voicing_style` and `voice_leading` keyword args, included in the returned plan dict.
- Wired `chord_pattern` consumption in the sequence builder (`sequence.py`): the groove's `chord_pattern` list now drives multi-hit chord events per slot with beat offsets and velocity scaling.
- Added `_apply_expression` post-processing pass (`sequence.py`): applies swing (off-beat eighth shift), humanize (deterministic RNG timing jitter), and velocity variance to all non-count-in events. Controllable via `expression_seed` for reproducibility.
- Refactored MIDI export to stem-separated tracks (`midi_export.py`): Type 1 SMF now outputs 3-5 tracks (tempo, chord stem, bass stem, optional count-in, optional drums on GM percussion channel 9) with program change events and time signature meta-events.
- Added `chord_program` and `bass_program` fields to all groove presets for GM instrument assignment.
- Activated non-zero expression values across groove presets: anthem (humanize 8ms, variance 6), pulse (humanize 4ms, variance 4, 4-hit chord pattern), lantern (swing 0.3, humanize 6ms, variance 8, 2-hit pattern), pads (unchanged, clean baseline).
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
- Latest verified result during this track: `392 passed, 1 skipped`

## Next Steps

### Phase 4 Second Batch: Tone and Live-Input Exploration

- Add live-input experiments on top of the transport and fretboard targets.
- Explore NAM/IR insertion where believable source audio exists.
- Keep the transport planner independent from the eventual tone engine.
- Explore per-channel program changes during live playback.

Why this matters:
- The hard part of the broader idea is not chart parsing; it is source realism, routing, and UX layering around playback.
- Phase 4 first batch's GUI exposure, voicing controls, and drum patterns make the arrangement surface feature-complete for sketching.
- Voice-led drop voicings combined with arpeggio patterns and drum grooves now produce output comparable to a competent arranger sketch.

### Explicitly Deferred

- Splitting the embedded frontend `_HTML` into separate assets.
- Full NAM integration and tone-browser workflows.
- Replacing `_DEFAULT_APP` usage across the whole module in one large change.
- Any large GUI asset split or framework migration while the transport contract is still moving.
