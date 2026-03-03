# Nashville Numbers Converter

Convert between chord progressions and Nashville Number System (NNS) from the command line.

## Install

```bash
pip install -e .
```

## Usage

```bash
nns-convert "C - F - G"
```

### Supported input styles

#### CHORDS → NNS

```bash
nns-convert "C - F - G"
nns-convert "| C | F G | Am |"
nns-convert "Cmaj7#11/G, Dm7, G7"
```

#### NNS → CHORDS (key required)

```bash
nns-convert "1 - 4 - 5 in G"
nns-convert "Key: Eb Major; 1 6 2 5"
nns-convert "1m - b7 - 4m - 5(7) in A minor"
```

If key is missing in NNS mode, output is exactly:

```text
Key: REQUIRED
```


## Maintainer checks

Run the CI-equivalent test command locally:

```bash
pytest -q
```
