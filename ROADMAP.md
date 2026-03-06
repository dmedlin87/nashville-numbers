# ROADMAP

This file is the canonical project roadmap.

## Status

Current active work is a low-risk GUI boundary cleanup intended to make future refactors safer without changing product behavior.

## Current Refactor Track

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
- Latest verified result during this refactor track: `147 passed, 1 skipped`

## Next Steps

### Phase 1: Finish GUI Boundary Isolation

- Add a small `create_default_app()` factory so production wiring stops depending on the module singleton directly.
- Update GUI tests to instantiate `GuiApp` directly where practical instead of always using `_DEFAULT_APP`.
- Keep `main()` as a thin entrypoint that delegates to the default app factory.

Why this is next:
- It removes the last meaningful coupling between module import state and app runtime state.
- It improves test setup clarity without touching routes or embedded frontend behavior.

### Phase 2: Keep Behavior Stable While Improving Seams

- Maintain the current embedded `_HTML` frontend and `/convert` plus `/audio/*` contracts unchanged.
- Continue using characterization tests as the guardrail before any structural moves.

Why this matters:
- The remaining risk is not core conversion logic; it is GUI/runtime orchestration and string-coupled UI/server behavior.

### Explicitly Deferred

- Splitting the embedded frontend `_HTML` into separate assets.
- Reworking the GUI route contract.
- Replacing `_DEFAULT_APP` usage across the whole module in one large change.
- Any audio runtime/install behavior change beyond testability and boundary cleanup.
