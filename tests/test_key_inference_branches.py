from __future__ import annotations

from nashville_numbers import key_inference
from nashville_numbers.key_inference import KeyChoice, ScoredKey, _score_key, infer_keys, infer_sections
from nashville_numbers.parser import ProgressionToken


def test_infer_keys_inserts_relative_key_when_close_and_not_in_top_slice(
    monkeypatch,
) -> None:
    ranked = [
        ScoredKey(KeyChoice("C", "Major"), 10.0),
        ScoredKey(KeyChoice("Db", "Major"), 9.8),
        ScoredKey(KeyChoice("D", "Major"), 9.7),
        ScoredKey(KeyChoice("A", "Minor"), 8.9),
    ]
    monkeypatch.setattr(key_inference, "rank_keys", lambda _prog: ranked)

    assert infer_keys("C F G", max_keys=3) == [
        KeyChoice("C", "Major"),
        KeyChoice("A", "Minor"),
        KeyChoice("Db", "Major"),
    ]


def test_infer_sections_falls_back_when_some_segments_cannot_be_ranked(
    monkeypatch,
) -> None:
    def fake_rank_keys(segment: str) -> list[ScoredKey]:
        stripped = segment.strip()
        if stripped in {"D", "E"}:
            return []
        return [
            ScoredKey(KeyChoice("C", "Major"), 2.0),
            ScoredKey(KeyChoice("G", "Major"), 0.0),
        ]

    monkeypatch.setattr(key_inference, "rank_keys", fake_rank_keys)

    progression = "C | D | E | F"
    assert infer_sections(progression) == [(progression, KeyChoice("C", "Major"))]


def test_infer_sections_falls_back_when_split_would_make_empty_segment(
    monkeypatch,
) -> None:
    monkeypatch.setattr(key_inference.re, "split", lambda _pattern, _prog: ["C", "D", "   ", "   "])
    monkeypatch.setattr(
        key_inference,
        "tokenize_progression",
        lambda _piece: [ProgressionToken("X", "chord")],
    )

    def fake_rank_keys(segment: str) -> list[ScoredKey]:
        if segment == "C":
            return [
                ScoredKey(KeyChoice("C", "Major"), 5.0),
                ScoredKey(KeyChoice("G", "Major"), 0.0),
            ]
        if segment == "D":
            return [
                ScoredKey(KeyChoice("C", "Major"), 5.0),
                ScoredKey(KeyChoice("G", "Major"), 0.0),
            ]
        if segment.strip() == "":
            return [
                ScoredKey(KeyChoice("D", "Major"), 5.0),
                ScoredKey(KeyChoice("A", "Major"), 0.0),
            ]
        return [
            ScoredKey(KeyChoice("F", "Major"), 5.0),
            ScoredKey(KeyChoice("C", "Major"), 0.0),
        ]

    monkeypatch.setattr(key_inference, "rank_keys", fake_rank_keys)

    progression = "ignored"
    assert infer_sections(progression) == [(progression, KeyChoice("F", "Major"))]


def test_score_key_rewards_leading_tone_diminished_chord_in_major() -> None:
    diminished = [("B", "dim", False, True, False)]
    plain = [("B", "", False, False, False)]
    assert _score_key(diminished, "C", "Major") > _score_key(plain, "C", "Major")
