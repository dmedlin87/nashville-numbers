"""Download and install default free SoundFont packs."""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .errors import AudioInstallError


@dataclass(frozen=True)
class PackManifest:
    id: str
    url: str
    soundfont_file: str
    notice_text: str


DEFAULT_PACK = PackManifest(
    id="fluidr3_gm",
    url="https://keymusician01.s3.amazonaws.com/FluidR3_GM.zip",
    soundfont_file="FluidR3_GM.sf2",
    notice_text=(
        "FluidR3 GM SoundFont\n"
        "Source: https://keymusician01.s3.amazonaws.com/FluidR3_GM.zip\n"
        "This pack is provided as a free General MIDI sound set.\n"
        "Include upstream attribution/readme files when redistributing this pack."
    ),
)


class DefaultPackInstaller:
    """Installs the default FluidR3 pack under ~/.nashville_numbers."""

    def __init__(self, root_dir: Path, manifest: PackManifest = DEFAULT_PACK) -> None:
        self.root_dir = root_dir
        self.manifest = manifest
        self.pack_root = self.root_dir / "packs" / self.manifest.id
        self.temp_root = self.root_dir / "tmp"

    def install_default(self) -> Path:
        existing = self._find_soundfont(self.pack_root)
        if existing is not None:
            self._write_notice(self.pack_root)
            return existing

        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        archive_path = self.temp_root / f"{self.manifest.id}.zip"

        try:
            with urlopen(self.manifest.url, timeout=90) as response, archive_path.open("wb") as out:
                shutil.copyfileobj(response, out)
        except URLError as exc:
            raise AudioInstallError("download_failed", f"Failed to download default sound pack: {exc}") from exc
        except OSError as exc:
            raise AudioInstallError("download_failed", f"Unable to write downloaded sound pack: {exc}") from exc

        if self.pack_root.exists():
            shutil.rmtree(self.pack_root, ignore_errors=True)
        self.pack_root.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(archive_path, "r") as zip_file:
                for member in zip_file.infolist():
                    target_path = Path(self.pack_root) / member.filename
                    if not target_path.resolve().is_relative_to(self.pack_root.resolve()):
                        raise AudioInstallError("invalid_pack", f"Zip slip detected in archive: {member.filename}")
                    zip_file.extract(member, self.pack_root)
        except zipfile.BadZipFile as exc:
            raise AudioInstallError("invalid_pack", "Downloaded pack archive is invalid") from exc
        finally:
            archive_path.unlink(missing_ok=True)

        soundfont_path = self._find_soundfont(self.pack_root)
        if soundfont_path is None:
            raise AudioInstallError(
                "invalid_pack",
                f"Downloaded pack did not contain {self.manifest.soundfont_file}",
            )

        self._write_notice(self.pack_root)
        metadata = {
            "id": self.manifest.id,
            "url": self.manifest.url,
            "soundfont_path": str(soundfont_path),
        }
        (self.pack_root / "pack.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return soundfont_path

    def status(self) -> dict[str, object]:
        soundfont_path = self._find_soundfont(self.pack_root)
        return {
            "id": self.manifest.id,
            "installed": soundfont_path is not None,
            "path": str(soundfont_path) if soundfont_path is not None else None,
        }

    def _write_notice(self, pack_dir: Path) -> None:
        notice_path = pack_dir / "THIRD_PARTY_NOTICE.txt"
        notice_path.write_text(self.manifest.notice_text + "\n", encoding="utf-8")

    def _find_soundfont(self, root: Path) -> Path | None:
        if not root.exists():
            return None
        direct = root / self.manifest.soundfont_file
        if direct.exists():
            return direct
        candidates = list(root.rglob(self.manifest.soundfont_file))
        return candidates[0] if candidates else None

