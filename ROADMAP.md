# ROADMAP

This file is the canonical project roadmap.

## Current Baseline

- Nashville Numbers conversion, key inference, CLI workflows, and the single-page GUI are stable.
- Music Lab transport is shipped: charts map into sections, bars, slots, groove-aware timing, count-ins, and loopable arrangement playback.
- All 9 groove presets are exposed in the GUI, with chord-pattern playback, arpeggios, walking bass, and drum-pattern-backed percussion support.
- Voicing style (`close`, `drop2`, `drop3`) and voice leading are wired end-to-end across the GUI, HTTP layer, planner, sequence builder, and MIDI export.
- MIDI export produces Type 1 multi-track files with tempo, chord, bass, count-in, and drum tracks.
- HQ audio uses the optional FluidSynth runtime when available and falls back to browser `web_tone` playback when it is not.

## Current Safety Baseline

- Verified on March 7, 2026: `python -m pytest -q`
- Result: `392 passed, 1 skipped, 2 warnings`

## Roadmap

### Phase 4B: Tone Foundation and Preview

- Add a local tone-import path for `.nam` models and optional `.wav` IRs, stored as user-managed assets rather than repo content.
- Parse and display tone metadata early: model name, version, architecture, sample-rate hints, and compatibility status.
- Build a browser/Web Audio preview lane that can audition DI preview clips through NAM plus optional IR without altering the existing FluidSynth arrangement path.
- Keep tone preview attached to the existing Music Lab surface so tone slots can eventually map to section or part assignments.
- Treat this phase as the first proof that NAM belongs in the app: tone preview ships before live-input polish or generated accompaniment.

### Phase 5: Live Input Practice Rig

- Add device/input selection, input meter, monitoring toggle, and latency-facing status in the browser audio path.
- Route live input and backing playback through one browser-side mix engine when live input is active so monitoring and transport stay in sync.
- Reuse the existing bar-and-section transport for looped-bar practice, count-ins, and progression-targeted play-along.
- Keep the initial scope to practice workflows: live monitoring, tone auditioning, and loop control, not recording or multitrack editing.

### Phase 6: User-Directed Tone Library Integration

- Explore TONE3000 integration only through user-authenticated, user-directed flows such as Select/API-backed tone picking.
- Persist imported or downloaded tone references locally with license and attribution metadata visible in the UI.
- Support starter tone organization inside the app: categories, favorites, and reusable tone assignments, without mirroring a public catalog.
- Keep tone acquisition separable from playback so manual local imports remain a first-class path.

### Phase 7: Generated Accompaniment Through NAM

- Add believable DI source layers for generated parts before tone processing, starting with narrow-scope DI guitar and DI bass playback experiments.
- Allow per-part tone assignment so rhythm guitar, arpeggio parts, and bass can route through different tone chains.
- Keep `music_lab.py` and `sequence.py` authoritative for musical intent and timed events; the NAM layer should render those decisions, not replace them.
- Expand only after DI source realism is credible enough to justify NAM processing on generated accompaniment.

## Roadmap Guardrails

- Keep transport, planning, and sequencing independent from tone rendering so the current playback stack and future tone engines can coexist.
- Treat tones and IRs as user-managed assets; do not promise bulk download, catalog mirroring, or redistribution workflows.
- Make NAM support version-aware and architecture-aware so the app can tolerate ecosystem changes without a rewrite.
- Keep the product out of full-DAW scope; favor practice, arrangement, fretboard, and harmony workflows over general recording or editing features.

## Explicitly Deferred / Not Yet

- Native DSP rewrites or a Python-embedded NAM engine before the browser/Web Audio tone path proves out.
- Bundled third-party tone libraries, mirrored public catalogs, or unrestricted public-tone browsing inside the app.
- Broad GUI framework migrations or large frontend asset splits while the tone path and live-input UX are still moving.
- Generated full-song backing production beyond the current arrangement sketchpad until DI source realism and routing are validated.

## Later Music Expansion

- After tone preview and live-input fundamentals land, the next expansion lane is deeper music behavior: section and song-form planning, backing-track exports and stems, richer practice workflows, and a constrained composer/theory surface that stays clearly short of a full DAW.
