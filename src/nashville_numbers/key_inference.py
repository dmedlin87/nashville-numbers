"""Deterministic key inference utilities."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass

from .parser import tokenize_progression

NOTE_TO_SEMITONE = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}

CANONICAL_TONICS = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
SEMITONE_TO_CANONICAL = {NOTE_TO_SEMITONE[t]: t for t in CANONICAL_TONICS}
MAJOR_SCALE = {0, 2, 4, 5, 7, 9, 11}
MINOR_SCALE = {0, 2, 3, 5, 7, 8, 10}

CHORD_RE = re.compile(r"^([A-G](?:#|b)?)([^/]*)?(?:/([A-G](?:#|b)?))?$")


@dataclass(frozen=True)
class KeyChoice:
    tonic: str
    mode: str


@dataclass(frozen=True)
class ScoredKey:
    choice: KeyChoice
    score: float


def infer_keys(prog: str, max_keys: int = 3) -> list[KeyChoice]:
    scored = rank_keys(prog)
    if not scored:
        return [KeyChoice("C", "Major")]

    best = scored[:max_keys]
    top = best[0]
    relative = KeyChoice(_relative_minor(top.choice.tonic), "Minor") if top.choice.mode == "Major" else KeyChoice(_relative_major(top.choice.tonic), "Major")
    rel_score = next((item for item in scored if item.choice == relative), None)
    if rel_score and rel_score.score >= top.score - 1.5 and relative not in [b.choice for b in best]:
        best = [top, rel_score, *best[1:]]
        best = best[:max_keys]

    return [item.choice for item in best]


# Cache expensive string tokenization and key scoring during section splits.
# infer_sections iteratively splits progression strings and repeatedly re-scores
# the same sub-strings, making this a prime candidate for memoization.
@functools.lru_cache(maxsize=1024)
def rank_keys(prog: str) -> list[ScoredKey]:
    chords = _extract_chords(prog)
    if not chords:
        return []

    scored: list[ScoredKey] = []
    for tonic in CANONICAL_TONICS:
        scored.append(ScoredKey(KeyChoice(tonic, "Major"), _score_key(chords, tonic, "Major")))
        scored.append(ScoredKey(KeyChoice(tonic, "Minor"), _score_key(chords, tonic, "Minor")))

    scored.sort(key=lambda item: (-item.score, item.choice.tonic, item.choice.mode))
    return scored


def infer_sections(prog: str) -> list[tuple[str, KeyChoice]]:
    pieces = re.split(r"(\|+)", prog)
    musical_indexes = [i for i, piece in enumerate(pieces) if piece and "|" not in piece and any(t.kind == "chord" for t in tokenize_progression(piece))]
    if len(musical_indexes) < 3:
        return [(prog, infer_keys(prog, max_keys=1)[0])]

    candidates: list[tuple[int, ScoredKey, float]] = []
    for idx in musical_indexes:
        ranking = rank_keys(pieces[idx])
        if not ranking:
            continue
        top = ranking[0]
        margin = top.score - (ranking[1].score if len(ranking) > 1 else 0.0)
        candidates.append((idx, top, margin))

    if len(candidates) < 3:
        return [(prog, infer_keys(prog, max_keys=1)[0])]

    first_key = candidates[0][1].choice
    switch_at: int | None = None
    for pos in range(1, len(candidates) - 1):
        curr = candidates[pos]
        nxt = candidates[pos + 1]
        if curr[1].choice == first_key:
            continue
        if curr[2] >= 2.0 and nxt[2] >= 2.0 and curr[1].choice == nxt[1].choice:
            switch_at = curr[0]
            break

    if switch_at is None:
        return [(prog, infer_keys(prog, max_keys=1)[0])]

    split_point = switch_at
    first = "".join(pieces[:split_point]).strip()
    second = "".join(pieces[split_point:]).strip()
    if not first or not second:
        return [(prog, infer_keys(prog, max_keys=1)[0])]

    return [
        (first, infer_keys(first, max_keys=1)[0]),
        (second, infer_keys(second, max_keys=1)[0]),
    ]


def _extract_chords(prog: str) -> list[tuple[int, str, bool, bool, bool]]:
    chords: list[tuple[int, str, bool, bool, bool]] = []
    for token in tokenize_progression(prog):
        if token.kind != "chord":
            continue
        match = CHORD_RE.match(token.text.strip())
        if not match:
            continue
        root = match.group(1)
        quality = (match.group(2) or "").lower()

        is_minor_quality = quality.startswith("m") and not quality.startswith("maj")
        is_dim_quality = "dim" in quality or "°" in quality or "m7b5" in quality
        is_dom_quality = "7" in quality and not quality.startswith("maj")

        chords.append((NOTE_TO_SEMITONE[root], quality, is_minor_quality, is_dim_quality, is_dom_quality))
    return chords


def _score_key(chords: list[tuple[int, str, bool, bool, bool]], tonic: str, mode: str) -> float:
    tonic_val = NOTE_TO_SEMITONE[tonic]
    score = 0.0
    scale = MAJOR_SCALE if mode == "Major" else MINOR_SCALE

    for root_val, quality, is_minor_quality, is_dim_quality, is_dom_quality in chords:
        semitone = (root_val - tonic_val) % 12
        in_scale = semitone in scale
        score += 2.5 if in_scale else -2.0

        if semitone == 0:
            score += 2.0
        elif semitone == 7:
            score += 1.5
        elif semitone in (5, 2):
            score += 1.0

        if mode == "Major":
            if semitone in (2, 4, 9) and is_minor_quality:
                score += 1.0
            if semitone == 11 and is_dim_quality:
                score += 1.0
            if semitone in (0, 5, 7) and not is_minor_quality:
                score += 0.7
        else:
            if semitone in (0, 5) and is_minor_quality:
                score += 1.0
            if semitone in (3, 8, 10) and not is_minor_quality:
                score += 0.7
            if semitone == 7 and (is_dom_quality or (quality and not is_minor_quality)):
                score += 1.8

    return round(score, 4)


def _relative_minor(major: str) -> str:
    semitone = (NOTE_TO_SEMITONE[major] + 9) % 12
    return _semitone_to_name(semitone)


def _relative_major(minor: str) -> str:
    semitone = (NOTE_TO_SEMITONE[minor] + 3) % 12
    return _semitone_to_name(semitone)


def _semitone_to_name(semitone: int) -> str:
    return SEMITONE_TO_CANONICAL.get(semitone, "C")
