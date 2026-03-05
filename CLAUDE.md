# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nashville Numbers Converter — a Python package that converts between standard chord progressions and the Nashville Number System (NNS). Two entry points: a CLI (`nns-convert`) and a browser/native-window GUI (`nns-gui`).

## Setup & Commands

```bash
# Install in editable mode (use the .venv)
pip install -e .

# Run tests
pytest -q

# Run a single test file
pytest tests/test_parser.py -q

# Run a specific test
pytest tests/test_conversion_golden.py::test_chords_to_nns_golden_examples -q

# CLI
nns-convert "C - F - G"
nns-convert "1 - 4 - 5 in G"

# GUI (starts local HTTP server, opens pywebview window or falls back to browser)
nns-gui
```

No separate build step — the package is pure Python.

## Architecture

The conversion pipeline flows through four modules:

```text
user input
    │
    ▼
parser.py        – tokenize + detect mode (chords_to_nns vs nns_to_chords)
    │                also extracts key/tonic if explicitly provided
    ▼
converter.py     – orchestrates the conversion
    │                calls key_inference when no key is given
    ▼
key_inference.py – scores all 24 keys (12 major × 12 minor) heuristically
    │                returns up to 3 candidates; detects section modulations
    ▼
output_contract.py – formats one or more OutputBlock(tonic, mode, progression)
                     into the canonical "Key: X Y\n<progression>" string
```

### Mode detection (`parser.py`)

`parse_input` counts NNS tokens vs chord tokens after stripping any key declaration. If NNS hits > chord hits, or if NNS tokens exist and a key is explicitly provided, the mode is `nns_to_chords`; otherwise `chords_to_nns`.

### Key inference (`key_inference.py`)

`rank_keys` scores every candidate key by checking how well chord roots fit the scale (+2.5 in-scale / −2.0 out) plus tonic/quality bonuses. `infer_sections` can detect a single key modulation by splitting on `|` separators and looking for a sustained scoring shift with margin ≥ 2.0. `rank_keys` is `@lru_cache`'d because `infer_sections` calls it repeatedly on the same sub-strings.

### Ambiguous output

When no key is given for chords→NNS, the converter returns **up to 3 key interpretations**, each as a separate `Key: X Y\n<progression>` block separated by a blank line. The relative major/minor pair is promoted if its score is within 1.5 points of the top choice.

### GUI (`gui.py`)

The entire front-end is a single embedded HTML string (`_HTML`) — no separate asset files. The Python layer is a minimal `http.server.BaseHTTPRequestHandler` serving `GET /` (the SPA) and `POST /convert` (JSON API calling `convert()`). `pywebview` is used for a native desktop window; if unavailable it falls back to `webbrowser.open`. The server enforces `MAX_INPUT_LENGTH = 1_000_000` and validates the JSON payload is a dict before accessing fields.

## Output Contract

Every successful result follows this exact format:

```text
Key: <Tonic> <Mode>
<converted progression>
```

Multi-key results are separated by `\n\n`. The `"Key: REQUIRED"` literal is the sole output when NNS→chords is requested without a key.

## Separator Preservation

Separators (` - `, ` | `, `,`, whitespace) are preserved verbatim in output. Tokenization splits on `SEPARATOR_CHARS = {' ', '\t', '\n', '\r', ',', '-', '|'}` but treats runs of those characters as a single separator token, which is passed through unchanged during conversion.

## Tests

| File                        | What it covers                                                                   |
|-----------------------------|----------------------------------------------------------------------------------|
| `test_conversion_golden.py` | End-to-end golden outputs for key conversion cases                               |
| `test_parser.py`            | Tokenization and `parse_input` mode/key detection                                |
| `test_key_inference.py`     | Scoring, ranking, section detection internals                                    |
| `test_input_limit.py`       | `MAX_INPUT_LENGTH` enforcement                                                   |
| `test_security.py`          | ReDoS safety: both parser regexes must complete in < 100ms on 5000-char payloads |
| `test_spelling.py`          | Output format consistency                                                        |
| `test_cli.py`               | CLI behaviour                                                                    |

Golden tests in `test_conversion_golden.py` are the primary regression guard — update them when intentionally changing output.
