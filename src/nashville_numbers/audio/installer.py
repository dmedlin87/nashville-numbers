"""Download and install default free SoundFont packs and FluidSynth runtime."""

from __future__ import annotations

import importlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import DEFAULT_AUDIO_ROOT
from .errors import AudioInstallError
from .runtime_support import import_fluidsynth_module, prepare_fluidsynth_environment

_FLUIDSYNTH_RELEASES_API = "https://api.github.com/repos/FluidSynth/fluidsynth/releases"
_HTTP_HEADERS = {"User-Agent": "nashville-numbers"}


@dataclass(frozen=True)
class PackManifest:
    id: str
    url: str
    soundfont_file: str
    notice_text: str


@dataclass(frozen=True)
class RuntimeAsset:
    tag_name: str
    name: str
    download_url: str


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

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or DEFAULT_AUDIO_ROOT
        self.runtime_root = self.root_dir / "runtime" / "fluidsynth"
        self.temp_root = self.root_dir / "tmp"
        self._last_runtime_error: str | None = None
        self._last_command_error: str | None = None
        self._last_binding_error: str | None = None

    def status(self) -> dict[str, object]:
        """Return current availability of runtime binary and Python binding."""
        snapshot = prepare_fluidsynth_environment(self.root_dir)
        return {
            "runtime_binary": bool(snapshot["runtime_ready"]),
            "python_binding": self._check_python_binding(),
            "runtime_path": snapshot.get("binary_path"),
            "library_path": snapshot.get("library_path"),
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

        self._last_runtime_error = None
        self._last_binding_error = None
        _progress(5, "Checking current installation…")
        system = platform.system()
        snapshot = prepare_fluidsynth_environment(self.root_dir)
        runtime_ok = bool(snapshot["runtime_ready"])

        if not runtime_ok:
            _progress(15, "Installing FluidSynth runtime…")
            runtime_ok = self._install_runtime(system, on_progress=_progress)
            snapshot = prepare_fluidsynth_environment(self.root_dir)
            runtime_ok = bool(snapshot["runtime_ready"])
        else:
            _progress(40, "Runtime already installed")

        _progress(50, "Checking Python binding…")
        binding_ok = self._check_python_binding()
        binding_error = self._last_binding_error
        binding_present = importlib.util.find_spec("fluidsynth") is not None
        if not binding_ok and (runtime_ok or not binding_present):
            _progress(60, "Installing Python binding (pip)…")
            self._install_python_binding()
            importlib.invalidate_caches()
            sys.modules.pop("fluidsynth", None)
            binding_ok = self._check_python_binding()
            binding_error = self._last_binding_error

        ready = runtime_ok and binding_ok
        _progress(100, "Done" if ready else "Finished with errors")

        if ready:
            message = "FluidSynth runtime and Python binding are ready."
        elif runtime_ok and not binding_ok:
            message = "FluidSynth runtime is available, but the Python binding is still unavailable."
        elif not runtime_ok and binding_ok:
            message = "Python binding is ready, but the FluidSynth runtime could not be installed automatically."
        else:
            message = "Could not make FluidSynth available automatically."

        if not runtime_ok and self._last_runtime_error:
            message = f"{message} {self._last_runtime_error}"
        if not binding_ok and binding_error:
            message = f"{message} Binding error: {binding_error}"

        return {
            "runtime_binary": runtime_ok,
            "python_binding": binding_ok,
            "ready": ready,
            "message": message,
            "runtime_path": snapshot.get("binary_path"),
            "library_path": snapshot.get("library_path"),
            "runtime_error": self._last_runtime_error,
            "binding_error": binding_error,
        }

    def _check_python_binding(self) -> bool:
        try:
            import_fluidsynth_module(self.root_dir)
            self._last_binding_error = None
            return True
        except Exception as exc:
            self._last_binding_error = str(exc)
            return False

    def _install_runtime(self, system: str, on_progress=None) -> bool:
        if system == "Windows":
            return self._try_windows(on_progress=on_progress)
        if system == "Darwin":
            ok = self._try_command(["brew", "install", "fluid-synth"])
            if not ok and self._last_command_error:
                self._last_runtime_error = self._last_command_error
            return ok
        # Linux: try common package managers
        for cmd in (
            ["apt-get", "install", "-y", "fluidsynth"],
            ["dnf", "install", "-y", "fluid-synth"],
            ["pacman", "-S", "--noconfirm", "fluidsynth"],
        ):
            if shutil.which(cmd[0]) and self._try_command(cmd):
                return True
            if self._last_command_error:
                self._last_runtime_error = self._last_command_error
        return False

    def _try_windows(self, on_progress=None) -> bool:
        if self._install_windows_portable(on_progress=on_progress):
            return True
        if shutil.which("choco") and self._try_command(["choco", "install", "fluidsynth", "-y"]):
            return True
        if self._last_command_error:
            self._last_runtime_error = self._last_command_error
        return False

    def _try_command(self, cmd: list[str]) -> bool:
        self._last_command_error = None
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            output = (result.stderr or result.stdout or "").strip()
            if result.returncode != 0:
                self._last_command_error = output or f"Command exited with status {result.returncode}."
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self._last_command_error = "Command timed out."
            return False
        except FileNotFoundError:
            self._last_command_error = "Required command was not found."
            return False
        except OSError as exc:
            self._last_command_error = str(exc)
            return False

    def _install_python_binding(self) -> bool:
        return self._try_command([sys.executable, "-m", "pip", "install", "pyfluidsynth>=1.3"])

    def _install_windows_portable(self, on_progress=None) -> bool:
        try:
            asset = self._find_windows_asset()
        except AudioInstallError as exc:
            self._last_runtime_error = str(exc)
            return False

        archive_path = self.temp_root / asset.name
        staging_root = self.temp_root / "fluidsynth-runtime"
        final_root = self.runtime_root

        self.temp_root.mkdir(parents=True, exist_ok=True)
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        staging_root.mkdir(parents=True, exist_ok=True)

        if on_progress is not None:
            on_progress(22, f"Downloading {asset.tag_name} runtime…")
        try:
            request = Request(asset.download_url, headers=_HTTP_HEADERS)
            with urlopen(request, timeout=90) as response, archive_path.open("wb") as out:
                shutil.copyfileobj(response, out)
        except (URLError, OSError) as exc:
            self._last_runtime_error = f"Failed to download portable FluidSynth runtime: {exc}"
            return False

        if on_progress is not None:
            on_progress(32, "Extracting runtime…")
        try:
            with zipfile.ZipFile(archive_path, "r") as zip_file:
                self._extract_zip(zip_file, staging_root)
        except (zipfile.BadZipFile, AudioInstallError) as exc:
            self._last_runtime_error = f"Portable runtime archive is invalid: {exc}"
            return False
        finally:
            archive_path.unlink(missing_ok=True)

        binary_found = any(staging_root.glob("**/fluidsynth.exe"))
        library_found = any(
            match.is_file()
            for pattern in ("**/libfluidsynth*.dll", "**/fluidsynth*.dll")
            for match in staging_root.glob(pattern)
        )
        if not (binary_found or library_found):
            self._last_runtime_error = "Portable runtime archive did not contain a FluidSynth executable or DLL."
            return False

        if final_root.exists():
            shutil.rmtree(final_root, ignore_errors=True)
        final_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging_root), str(final_root))

        metadata = {
            "source": "github_release",
            "tag_name": asset.tag_name,
            "asset_name": asset.name,
            "download_url": asset.download_url,
        }
        (final_root / "runtime.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        snapshot = prepare_fluidsynth_environment(self.root_dir)
        if snapshot["runtime_ready"]:
            return True

        self._last_runtime_error = "Portable runtime was downloaded, but the runtime could not be validated."
        return False

    def _find_windows_asset(self) -> RuntimeAsset:
        architecture = "x64" if sys.maxsize > 2**32 else "x86"
        preferred_suffixes = (
            f"win10-{architecture}-cpp11.zip",
            f"win10-{architecture}-glib.zip",
        )

        try:
            request = Request(_FLUIDSYNTH_RELEASES_API, headers=_HTTP_HEADERS)
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, OSError, json.JSONDecodeError) as exc:
            raise AudioInstallError("runtime_lookup_failed", f"Unable to query FluidSynth releases: {exc}") from exc

        if not isinstance(payload, list):
            raise AudioInstallError("runtime_lookup_failed", "Unexpected FluidSynth release response.")

        for release in payload:
            if not isinstance(release, dict):
                continue
            tag_name = str(release.get("tag_name", "")).strip()
            assets = release.get("assets")
            if not isinstance(assets, list):
                continue
            for suffix in preferred_suffixes:
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    name = str(asset.get("name", "")).strip()
                    download_url = str(asset.get("browser_download_url", "")).strip()
                    if name.endswith(suffix) and download_url:
                        return RuntimeAsset(tag_name=tag_name, name=name, download_url=download_url)

        raise AudioInstallError(
            "runtime_lookup_failed",
            "No compatible Windows FluidSynth runtime asset was found in the official release feed.",
        )

    def _extract_zip(self, zip_file: zipfile.ZipFile, destination: Path) -> None:
        for member in zip_file.infolist():
            target_path = destination / member.filename
            if not target_path.resolve().is_relative_to(destination.resolve()):
                raise AudioInstallError("invalid_pack", f"Zip slip detected in archive: {member.filename}")
            zip_file.extract(member, destination)
