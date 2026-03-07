"""Audio configuration loading, persistence, and install-state tracking."""

from __future__ import annotations

import json
import os
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_AUDIO_ROOT = Path.home() / ".nashville_numbers"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "soundfont_path": None,
    "quality": {
        "interpolation_default": 4,
        "interpolation_bass": 4,
        "reverb": {"roomsize": 0.45, "damping": 0.2, "width": 0.6, "level": 0.45},
        "chorus": {"nr": 3, "level": 1.6, "speed": 0.35, "depth_ms": 8.0, "type": 0},
    },
}


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
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


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


class AudioConfigStore:
    """Simple JSON config store at ~/.nashville_numbers/audio.json."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or DEFAULT_AUDIO_ROOT
        self.config_path = self.root_dir / "audio.json"
        self.pack_dir = self.root_dir / "packs"
        self._last_load_info: dict[str, Any] = {
            "valid": True,
            "reason": "ok",
            "quarantined_to": None,
        }

    def load(self) -> dict[str, Any]:
        data = deepcopy(DEFAULT_CONFIG)
        self._last_load_info = {"valid": True, "reason": "ok", "quarantined_to": None}
        if self.config_path.exists():
            try:
                parsed = json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                parsed = self._quarantine_invalid_config()
            if isinstance(parsed, dict):
                self._merge_known_fields(data, parsed)
            else:
                self._last_load_info = {
                    "valid": False,
                    "reason": "invalid_config",
                    "quarantined_to": self._last_load_info.get("quarantined_to"),
                }

        env_soundfont = os.getenv("NNS_SOUNDFONT_PATH", "").strip()
        if env_soundfont:
            data["soundfont_path"] = env_soundfont
        if _truthy(os.getenv("NNS_AUDIO_DISABLED")):
            data["enabled"] = False

        soundfont = data.get("soundfont_path")
        data["soundfont_path"] = str(soundfont).strip() if soundfont else None
        return data

    def save(self, config: dict[str, Any]) -> None:
        normalized = deepcopy(DEFAULT_CONFIG)
        self._merge_known_fields(normalized, config)
        _atomic_write_text(self.config_path, json.dumps(normalized, indent=2, sort_keys=True) + "\n")

    def _merge_known_fields(self, target: dict[str, Any], source: dict[str, Any]) -> None:
        if "enabled" in source:
            target["enabled"] = bool(source["enabled"])
        if "soundfont_path" in source:
            target["soundfont_path"] = source["soundfont_path"] or None
        source_quality = source.get("quality")
        if isinstance(source_quality, dict):
            quality = target.setdefault("quality", {})
            if "interpolation_default" in source_quality:
                quality["interpolation_default"] = int(source_quality["interpolation_default"])
            if "interpolation_bass" in source_quality:
                quality["interpolation_bass"] = int(source_quality["interpolation_bass"])
            for effect_name in ("reverb", "chorus"):
                effect_values = source_quality.get(effect_name)
                if isinstance(effect_values, dict):
                    quality.setdefault(effect_name, {}).update(effect_values)

    def load_info(self) -> dict[str, Any]:
        return dict(self._last_load_info)

    def _quarantine_invalid_config(self) -> dict[str, Any]:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        quarantine_path = self.root_dir / f"audio.invalid-{timestamp}.json"
        try:
            payload = self.config_path.read_text(encoding="utf-8")
        except OSError:
            payload = ""
        try:
            if payload:
                _atomic_write_text(quarantine_path, payload)
        except OSError:
            quarantine_path = None  # type: ignore[assignment]
        try:
            self.config_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._last_load_info = {
            "valid": False,
            "reason": "invalid_config",
            "quarantined_to": str(quarantine_path) if quarantine_path else None,
        }
        return {}


class InstallStateStore:
    """Persistent JSON status file for long-running audio install jobs."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or DEFAULT_AUDIO_ROOT
        self.state_path = self.root_dir / "install_state.json"

    def load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def save(self, state: dict[str, Any]) -> None:
        _atomic_write_text(self.state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")
