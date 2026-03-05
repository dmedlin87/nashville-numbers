# Audio Update (Near-Ultra Free Playback v1)

Date: 2026-03-05

## What Was Added

- New internal audio subsystem:
  - `src/nashville_numbers/audio/config.py`
  - `src/nashville_numbers/audio/scheduler.py`
  - `src/nashville_numbers/audio/engine.py`
  - `src/nashville_numbers/audio/installer.py`
  - `src/nashville_numbers/audio/service.py`
- GUI backend audio API routes in `src/nashville_numbers/gui.py`:
  - `GET /audio/status`
  - `POST /audio/install-default`
  - `POST /audio/play-note`
  - `POST /audio/note-on`
  - `POST /audio/note-off`
  - `POST /audio/play-chord`
  - `POST /audio/panic`
- Frontend audio behavior (embedded in `gui.py` HTML):
  - Audio status pill (`HQ Ready`, `HQ Missing`, `Web Tone Fallback`)
  - Install button for default free pack (`FluidR3_GM`)
  - Fretboard note press/hold playback (`pointerdown` -> `note_on`, release -> `note_off`)
  - Chord token click strum preview
  - WebAudio fallback synth (ADSR) when HQ backend is unavailable
- Optional dependency group in `pyproject.toml`:
  - `audio = ["pyfluidsynth>=1.3", "platformdirs>=4"]`
- Notices/docs:
  - `THIRD_PARTY_NOTICES.md`
  - README note for optional audio install

## Default Audio Strategy

- HQ path: `FluidSynth` runtime + `pyfluidsynth` Python binding.
- Default free pack: `FluidR3_GM` (installed on explicit user action only).
- Fallback path: browser WebAudio synth, so playback still works without native runtime.

## Install and Run (Windows)

1. Install FluidSynth runtime (system-level):
   - `winget install FluidSynth.FluidSynth`
   - fallback: `choco install fluidsynth -y`
2. Install Python audio extras in repo venv:
   - `pip install -e ".[audio]"`
3. Verify:
   - `fluidsynth --version`
   - `python -c "import fluidsynth; print('pyfluidsynth ok')"`
4. Start GUI:
   - `nns-gui`

## API Contracts (Current)

- `GET /audio/status`:
  - `hq_ready`, `engine`, `reason`, `fallback`, `pack`
- `POST /audio/install-default`:
  - installs default pack and returns `{ "status": ... }`
- `POST /audio/play-note`:
  - `midi`, `velocity`, `duration_ms`, `channel`
- `POST /audio/note-on`:
  - `midi`, optional `velocity`, optional `channel`
- `POST /audio/note-off`:
  - `midi`, optional `channel`
- `POST /audio/play-chord`:
  - `midis`, `style`, `strum_ms`, `note_ms`, `velocity`, `channel`
- `POST /audio/panic`:
  - all notes off + clear scheduled events

## Validation and Status Codes

- `400`: invalid payload/schema/ranges
- `409`: HQ unavailable (frontend should fallback)
- `500`: runtime/internal failure

## Config and Runtime Paths

- Config file:
  - `~/.nashville_numbers/audio.json`
- Env overrides:
  - `NNS_SOUNDFONT_PATH`
  - `NNS_AUDIO_DISABLED`
- Default pack directory:
  - `~/.nashville_numbers/packs/fluidr3_gm`

## Tests Added

- `tests/test_audio_scheduler.py`
- `tests/test_audio_engine.py`
- Expanded `tests/test_gui.py` with `/audio/*` route tests

## Current Limitations

- No backing track generator yet (explicitly deferred to phase 2).
- FluidSynth runtime is not automatically installed by Python package install.
- In-app runtime bootstrap for FluidSynth (especially Windows-first) is not implemented yet.

## Verification Snapshot

- Command: `python -m pytest -q`
- Result: `104 passed`

