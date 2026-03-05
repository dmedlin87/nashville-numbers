# Nashville Numbers Converter

> **The fastest way to speak Music's secret language.**

![Nashville Numbers Jukebox](content/nashville-numbers-jutebox.png)

Talk to musicians the way musicians actually talk — in numbers. Throw in a chord progression, get back Nashville Numbers. Got a chart full of numbers and need real chords? Done. Works from the command line or a slick browser GUI, with zero setup beyond a single `pip install`.

---

## Documentation

- [ROADMAP.md](ROADMAP.md)
- [AGENTS.md](AGENTS.md)
- [CLAUDE.md](CLAUDE.md)

---

## Install

```bash
# from an activated .venv
pip install -e .
```

### Optional HQ audio dependencies

```bash
pip install -e ".[audio]"
```

The GUI includes a first-run installer for a free default SoundFont pack (`FluidR3_GM`) and falls back to browser tone playback when HQ audio is unavailable.

---

## GUI — point, click, play

```bash
nns-gui
```

Spins up a local server and pops open your browser automatically. No Electron, no npm, no drama — pure Python standard library.

---

## CLI — fast and no-nonsense

```bash
nns-convert "C - F - G"
```

### Chords → Nashville Numbers

```bash
nns-convert "C - F - G"
nns-convert "| C | F G | Am |"
nns-convert "Cmaj7#11/G, Dm7, G7"
```

### Nashville Numbers → Chords (key required)

```bash
nns-convert "1 - 4 - 5 in G"
nns-convert "Key: Eb Major; 1 6 2 5"
nns-convert "1m - b7 - 4m - 5(7) in A minor"
```

Forget the key? You'll hear about it:

```
Key: REQUIRED
```

---

## Running tests

```bash
python -m pytest -q
```
