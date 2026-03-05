"""Audio configuration loading and persistence."""

from __future__ import annotations

import json
import os
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

    def load(self) -> dict[str, Any]:
        data = deepcopy(DEFAULT_CONFIG)
        if self.config_path.exists():
            try:
                parsed = json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                parsed = {}
            if isinstance(parsed, dict):
                self._merge_known_fields(data, parsed)

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
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")

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

