from __future__ import annotations

import json

import pytest

from nashville_numbers.tone_library import ToneLibrary, ToneLibraryError


def _valid_model(
    *,
    name: str = "Studio Tone",
    version: str | None = "0.9.0",
    architecture: str | None = "wavenet",
    sample_rate: int | None = 48000,
) -> bytes:
    payload: dict[str, object] = {"name": name, "weights": [1, 2, 3]}
    if version is not None:
        payload["version"] = version
    if architecture is not None:
        payload["architecture"] = architecture
    if sample_rate is not None:
        payload["sample_rate"] = sample_rate
    return json.dumps(payload).encode("utf-8")


def test_import_model_stores_file_and_manifest_entry(tmp_path) -> None:
    library = ToneLibrary(root_dir=tmp_path / "tones")

    tone = library.import_model(
        filename="clean.nam",
        data=_valid_model(),
        source_path="clean.nam",
    )

    assert tone["id"]
    assert tone["name"] == "Studio Tone"
    assert tone["compatibility"] == "compatible"
    assert (library.models_dir / tone["model_file"]).exists()

    listed = library.list_library()
    assert len(listed["tones"]) == 1
    assert listed["tones"][0]["id"] == tone["id"]


def test_import_model_with_missing_metadata_is_lenient(tmp_path) -> None:
    library = ToneLibrary(root_dir=tmp_path / "tones")

    tone = library.import_model(
        filename="missing-fields.nam",
        data=_valid_model(version=None, architecture=None),
    )

    assert tone["compatibility"] == "unknown"
    assert tone["metadata"]["version"] is None
    assert tone["metadata"]["architecture"] is None


def test_compatibility_classification_mapping(tmp_path) -> None:
    library = ToneLibrary(root_dir=tmp_path / "tones")
    assert library.classify_compatibility({"version": "0.9", "architecture": "wavenet"}) == "compatible"
    assert library.classify_compatibility({"version": "0.9", "architecture": "new-hotness"}) == "warning"
    assert library.classify_compatibility({"version": "0.9", "architecture": "unsupported"}) == "incompatible"
    assert library.classify_compatibility({}) == "unknown"


def test_import_ir_attach_detach_and_orphan_cleanup(tmp_path) -> None:
    library = ToneLibrary(root_dir=tmp_path / "tones")
    tone = library.import_model(filename="tone.nam", data=_valid_model())

    payload = library.import_ir(filename="cab.wav", data=b"RIFF....WAVE", tone_id=tone["id"])
    ir_id = payload["ir"]["id"]
    ir_file = payload["ir"]["file"]
    assert (library.irs_dir / ir_file).exists()

    detached = library.attach_ir(tone_id=tone["id"], ir_id=None)
    assert detached["ir_id"] is None
    assert detached["ir_file"] is None
    assert not (library.irs_dir / ir_file).exists()
    assert library.list_library()["irs"] == []


def test_remove_tone_cleans_orphan_ir_and_keeps_manifest_consistent(tmp_path) -> None:
    library = ToneLibrary(root_dir=tmp_path / "tones")
    tone = library.import_model(filename="tone.nam", data=_valid_model())
    payload = library.import_ir(filename="cab.wav", data=b"RIFF....WAVE", tone_id=tone["id"])
    ir_file = payload["ir"]["file"]

    result = library.remove_tone(tone_id=tone["id"])

    assert result["removed_id"] == tone["id"]
    assert result["library"]["tones"] == []
    assert result["library"]["irs"] == []
    assert not (library.irs_dir / ir_file).exists()


def test_manifest_persists_across_instances(tmp_path) -> None:
    root = tmp_path / "tones"
    library_a = ToneLibrary(root_dir=root)
    tone = library_a.import_model(filename="persist.nam", data=_valid_model(name="Persist Tone"))

    library_b = ToneLibrary(root_dir=root)
    listed = library_b.list_library()

    assert len(listed["tones"]) == 1
    assert listed["tones"][0]["id"] == tone["id"]
    assert listed["tones"][0]["name"] == "Persist Tone"


def test_import_model_rejects_non_json_binary(tmp_path) -> None:
    library = ToneLibrary(root_dir=tmp_path / "tones")
    with pytest.raises(ToneLibraryError) as exc:
        library.import_model(filename="bad.nam", data=b"\x00\xff")
    assert exc.value.code == "invalid_model_format"


def test_attach_ir_unknown_tone_raises(tmp_path) -> None:
    library = ToneLibrary(root_dir=tmp_path / "tones")
    with pytest.raises(ToneLibraryError) as exc:
        library.attach_ir(tone_id="missing", ir_id="x")
    assert exc.value.code == "tone_not_found"
