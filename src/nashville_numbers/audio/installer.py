"""Download and install default free SoundFont packs and FluidSynth runtime."""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .errors import AudioInstallError

# Known Windows locations where FluidSynth installers place the binary.
_WINDOWS_FLUIDSYNTH_PATHS = [
    r"C:\Program Files\FluidSynth\bin",
    r"C:\Program Files (x86)\FluidSynth\bin",
]


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


class RuntimeInstaller:
    """Detects and installs the FluidSynth C runtime and pyfluidsynth binding."""

    def status(self) -> dict[str, object]:
        """Return current availability of runtime binary and Python binding."""
        return {
            "runtime_binary": shutil.which("fluidsynth") is not None,
            "python_binding": self._check_python_binding(),
        }

    def install(self, on_progress=None) -> dict[str, object]:
        """Attempt to install the FluidSynth runtime and pyfluidsynth.

        Args:
            on_progress: optional callable(pct: int, stage: str) called at key
                         steps so callers can surface a progress indicator.

        Returns a dict with keys:
          - runtime_binary: bool  – runtime binary found after install attempt
          - python_binding: bool  – pyfluidsynth importable after install attempt
          - ready: bool           – both of the above are True
          - message: str          – human-readable summary
        """

        def _progress(pct: int, stage: str) -> None:
            if on_progress is not None:
                try:
                    on_progress(pct, stage)
                except Exception:
                    pass

        _progress(5, "Checking current installation…")
        system = platform.system()
        runtime_ok = shutil.which("fluidsynth") is not None

        if not runtime_ok:
            _progress(15, "Installing FluidSynth runtime…")
            runtime_ok = self._install_runtime(system)
            if runtime_ok and system == "Windows":
                _progress(48, "Configuring runtime paths…")
                self._patch_windows_path()
        else:
            _progress(40, "Runtime already installed")

        _progress(50, "Checking Python binding…")
        binding_ok = self._check_python_binding()
        if not binding_ok:
            _progress(60, "Installing Python binding (pip)…")
            binding_ok = self._install_python_binding()
            if binding_ok:
                importlib.invalidate_caches()

        ready = runtime_ok and binding_ok
        _progress(100, "Done" if ready else "Finished with errors")

        if ready:
            message = "FluidSynth runtime and Python binding are ready."
        elif runtime_ok and not binding_ok:
            message = "Runtime installed but Python binding (pyfluidsynth) could not be installed automatically."
        elif not runtime_ok and binding_ok:
            message = "Python binding ready but FluidSynth runtime could not be installed automatically. Install it manually and restart the app."
        else:
            message = "Could not install FluidSynth automatically. Install manually then restart the app."

        return {
            "runtime_binary": runtime_ok,
            "python_binding": binding_ok,
            "ready": ready,
            "message": message,
        }

    def _check_python_binding(self) -> bool:
        try:
            importlib.import_module("fluidsynth")
            return True
        except Exception:
            return False

    def _install_runtime(self, system: str) -> bool:
        if system == "Windows":
            return self._try_windows()
        if system == "Darwin":
            return self._try_command(["brew", "install", "fluid-synth"])
        # Linux: try common package managers
        for cmd in (
            ["apt-get", "install", "-y", "fluidsynth"],
            ["dnf", "install", "-y", "fluid-synth"],
            ["pacman", "-S", "--noconfirm", "fluidsynth"],
        ):
            if shutil.which(cmd[0]) and self._try_command(cmd):
                return True
        return False

    def _try_windows(self) -> bool:
        if shutil.which("winget") and self._try_command([
            "winget", "install", "-e", "--id", "FluidSynth.FluidSynth",
            "--accept-package-agreements", "--accept-source-agreements",
        ]):
            return True
        if shutil.which("choco") and self._try_command(["choco", "install", "fluidsynth", "-y"]):
            return True
        return False

    def _try_command(self, cmd: list[str]) -> bool:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=180)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _install_python_binding(self) -> bool:
        return self._try_command([sys.executable, "-m", "pip", "install", "pyfluidsynth>=1.3"])

    def _patch_windows_path(self) -> None:
        """Extend PATH with known Windows FluidSynth bin dirs so ctypes can load the DLL."""
        current = os.environ.get("PATH", "")
        additions = [p for p in _WINDOWS_FLUIDSYNTH_PATHS if os.path.isdir(p) and p not in current]
        if additions:
            os.environ["PATH"] = os.pathsep.join(additions) + os.pathsep + current
