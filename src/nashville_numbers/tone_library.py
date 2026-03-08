from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

DEFAULT_TONE_ROOT = Path.home() / ".nashville_numbers" / "tones"

_KNOWN_ARCHITECTURES = {
    "a2",
    "wavenet",
    "lstm",
    "convnet",
    "transformer",
}


@dataclass(slots=True)
class ToneLibraryError(Exception):
    code: str
    message: str
    status: int = 400

    def __str__(self) -> str:
        return self.message


class ToneLibrary:
    """Persistent user-managed tone library for NAM models and optional IR files."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or DEFAULT_TONE_ROOT
        self.models_dir = self.root_dir / "models"
        self.irs_dir = self.root_dir / "irs"
        self.manifest_path = self.root_dir / "library.json"
        self._lock = Lock()

    def list_library(self) -> dict[str, Any]:
        with self._lock:
            manifest = self._load_manifest()
            ir_file_by_id = self._ir_file_map(manifest)
            return {
                "tones": [self._public_tone(record, ir_file_by_id) for record in manifest["tones"]],
                "irs": [self._public_ir(record) for record in manifest["irs"]],
            }

    def import_model(self, *, filename: str, data: bytes, source_path: str | None = None) -> dict[str, Any]:
        safe_name = self._validate_extension(filename, {".nam"}, "invalid_extension")
        parsed = self._parse_nam_json(data)
        tone_id = self._new_id()
        stored_name = f"{tone_id}_{safe_name}"
        imported_at = _utc_now()

        metadata = self._extract_metadata(
            parsed,
            fallback_name=Path(safe_name).stem,
            source_path=source_path or filename,
            imported_at=imported_at,
        )

        model_path = self.models_dir / stored_name
        with self._lock:
            manifest = self._load_manifest()
            self._atomic_write_bytes(model_path, data)
            record = {
                "id": tone_id,
                "name": metadata["name"],
                "model_file": stored_name,
                "ir_id": None,
                "imported_at": imported_at,
                "metadata": metadata,
                "compatibility": self.classify_compatibility(metadata),
            }
            manifest["tones"].append(record)
            self._save_manifest(manifest)
            return self._public_tone(record, self._ir_file_map(manifest))

    def import_ir(
        self,
        *,
        filename: str,
        data: bytes,
        tone_id: str | None = None,
    ) -> dict[str, Any]:
        safe_name = self._validate_extension(filename, {".wav"}, "invalid_extension")
        ir_id = self._new_id()
        stored_name = f"{ir_id}_{safe_name}"
        imported_at = _utc_now()

        ir_path = self.irs_dir / stored_name
        with self._lock:
            manifest = self._load_manifest()
            self._atomic_write_bytes(ir_path, data)
            ir_record = {
                "id": ir_id,
                "name": Path(safe_name).stem,
                "file": stored_name,
                "imported_at": imported_at,
            }
            manifest["irs"].append(ir_record)

            updated_tone = None
            if tone_id:
                tone_record = self._find_tone(manifest, tone_id)
                if tone_record is None:
                    raise ToneLibraryError("tone_not_found", f"Unknown tone id: {tone_id}", status=404)
                tone_record["ir_id"] = ir_id
                updated_tone = tone_record

            self._save_manifest(manifest)
            payload: dict[str, Any] = {"ir": self._public_ir(ir_record)}
            if updated_tone is not None:
                payload["tone"] = self._public_tone(updated_tone, self._ir_file_map(manifest))
            return payload

    def attach_ir(self, *, tone_id: str, ir_id: str | None) -> dict[str, Any]:
        with self._lock:
            manifest = self._load_manifest()
            tone_record = self._find_tone(manifest, tone_id)
            if tone_record is None:
                raise ToneLibraryError("tone_not_found", f"Unknown tone id: {tone_id}", status=404)

            old_ir_id = tone_record.get("ir_id")
            if ir_id is None:
                tone_record["ir_id"] = None
                self._cleanup_orphan_ir(manifest, old_ir_id)
                self._save_manifest(manifest)
                return self._public_tone(tone_record, self._ir_file_map(manifest))

            ir_record = self._find_ir(manifest, ir_id)
            if ir_record is None:
                raise ToneLibraryError("ir_not_found", f"Unknown IR id: {ir_id}", status=404)

            tone_record["ir_id"] = ir_id
            self._cleanup_orphan_ir(manifest, old_ir_id)
            self._save_manifest(manifest)
            return self._public_tone(tone_record, self._ir_file_map(manifest))

    def remove_tone(self, *, tone_id: str) -> dict[str, Any]:
        with self._lock:
            manifest = self._load_manifest()
            index = self._find_tone_index(manifest, tone_id)
            if index is None:
                raise ToneLibraryError("tone_not_found", f"Unknown tone id: {tone_id}", status=404)

            tone_record = manifest["tones"].pop(index)
            model_file = str(tone_record.get("model_file", "")).strip()
            if model_file:
                (self.models_dir / model_file).unlink(missing_ok=True)

            self._cleanup_orphan_ir(manifest, tone_record.get("ir_id"))
            self._save_manifest(manifest)
            return {
                "removed_id": tone_id,
                "library": {
                    "tones": [
                        self._public_tone(record, self._ir_file_map(manifest))
                        for record in manifest["tones"]
                    ],
                    "irs": [self._public_ir(record) for record in manifest["irs"]],
                },
            }

    @staticmethod
    def classify_compatibility(metadata: dict[str, Any]) -> str:
        arch_raw = metadata.get("architecture")
        version_raw = metadata.get("version")

        arch = str(arch_raw).strip().lower() if arch_raw is not None else ""
        version = str(version_raw).strip() if version_raw is not None else ""

        if not arch and not version:
            return "unknown"
        if arch in {"unsupported", "invalid", "none"}:
            return "incompatible"
        if not arch or not version:
            return "warning"
        if arch not in _KNOWN_ARCHITECTURES:
            return "warning"
        return "compatible"

    def _extract_metadata(
        self,
        payload: dict[str, Any],
        *,
        fallback_name: str,
        source_path: str,
        imported_at: str,
    ) -> dict[str, Any]:
        metadata_block = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        version = payload.get("version")
        architecture = payload.get("architecture")
        sample_rate = (
            payload.get("sample_rate")
            if payload.get("sample_rate") is not None
            else metadata_block.get("sample_rate")
        )

        name = payload.get("name") or metadata_block.get("name") or fallback_name

        raw_fields: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"weights"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                raw_fields[key] = value

        return {
            "name": str(name).strip() or fallback_name,
            "version": version,
            "architecture": architecture,
            "sample_rate": sample_rate,
            "source_path": source_path,
            "imported_at": imported_at,
            "raw_fields": raw_fields,
        }

    def _load_manifest(self) -> dict[str, list[dict[str, Any]]]:
        if not self.manifest_path.exists():
            return {"tones": [], "irs": []}
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"tones": [], "irs": []}
        if not isinstance(payload, dict):
            return {"tones": [], "irs": []}
        tones = payload.get("tones")
        irs = payload.get("irs")
        return {
            "tones": tones if isinstance(tones, list) else [],
            "irs": irs if isinstance(irs, list) else [],
        }

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.irs_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        self._atomic_write_text(self.manifest_path, text)

    def _atomic_write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            temp_path.replace(path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _atomic_write_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            temp_path.replace(path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _parse_nam_json(self, data: bytes) -> dict[str, Any]:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToneLibraryError(
                "invalid_model_format",
                "Model must be UTF-8 JSON (.nam).",
                status=415,
            ) from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ToneLibraryError(
                "invalid_model_format",
                "Model JSON could not be parsed.",
                status=415,
            ) from exc
        if not isinstance(payload, dict):
            raise ToneLibraryError(
                "invalid_model_format",
                "Model JSON must be an object.",
                status=415,
            )
        return payload

    def _validate_extension(self, filename: str, allowed: set[str], code: str) -> str:
        name = _sanitize_filename(filename)
        ext = Path(name).suffix.lower()
        if ext not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise ToneLibraryError(code, f"Unsupported file type. Expected {allowed_text}.", status=415)
        return name

    def _new_id(self) -> str:
        return secrets.token_hex(8)

    def _find_tone(self, manifest: dict[str, Any], tone_id: str) -> dict[str, Any] | None:
        for record in manifest["tones"]:
            if str(record.get("id", "")) == tone_id:
                return record
        return None

    def _find_tone_index(self, manifest: dict[str, Any], tone_id: str) -> int | None:
        for idx, record in enumerate(manifest["tones"]):
            if str(record.get("id", "")) == tone_id:
                return idx
        return None

    def _find_ir(self, manifest: dict[str, Any], ir_id: str) -> dict[str, Any] | None:
        for record in manifest["irs"]:
            if str(record.get("id", "")) == ir_id:
                return record
        return None

    def _cleanup_orphan_ir(self, manifest: dict[str, Any], ir_id: Any) -> None:
        if not isinstance(ir_id, str) or not ir_id:
            return
        still_used = any(str(tone.get("ir_id", "")) == ir_id for tone in manifest["tones"])
        if still_used:
            return

        ir_index = None
        for idx, record in enumerate(manifest["irs"]):
            if str(record.get("id", "")) == ir_id:
                ir_index = idx
                break
        if ir_index is None:
            return

        ir_record = manifest["irs"].pop(ir_index)
        ir_file = str(ir_record.get("file", "")).strip()
        if ir_file:
            (self.irs_dir / ir_file).unlink(missing_ok=True)

    def _public_tone(self, tone: dict[str, Any], ir_file_by_id: dict[str, str]) -> dict[str, Any]:
        ir_file = None
        ir_id = tone.get("ir_id")
        if isinstance(ir_id, str) and ir_id:
            ir_file = ir_file_by_id.get(ir_id)

        return {
            "id": str(tone.get("id", "")),
            "name": str(tone.get("name", "") or ""),
            "model_file": str(tone.get("model_file", "")),
            "ir_file": ir_file,
            "metadata": tone.get("metadata", {}),
            "compatibility": str(tone.get("compatibility", "unknown")),
            "imported_at": str(tone.get("imported_at", "")),
            "ir_id": ir_id,
        }

    def _public_ir(self, ir: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(ir.get("id", "")),
            "name": str(ir.get("name", "")),
            "file": str(ir.get("file", "")),
            "imported_at": str(ir.get("imported_at", "")),
        }

    def _ir_file_map(self, manifest: dict[str, Any]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for record in manifest["irs"]:
            ir_id = str(record.get("id", "")).strip()
            ir_file = str(record.get("file", "")).strip()
            if ir_id and ir_file:
                mapping[ir_id] = ir_file
        return mapping


def _sanitize_filename(name: str) -> str:
    raw = Path(name or "upload").name
    if not raw:
        raw = "upload"
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", raw)
    return sanitized[:180] or "upload"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
