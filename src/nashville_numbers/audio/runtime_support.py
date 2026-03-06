"""FluidSynth runtime discovery and safe import helpers."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import DEFAULT_AUDIO_ROOT

_WINDOWS_BIN_HINTS = (
    Path(r"C:\Program Files\FluidSynth\bin"),
    Path(r"C:\Program Files (x86)\FluidSynth\bin"),
)
_WINDOWS_DLL_GLOBS = ("libfluidsynth*.dll", "fluidsynth*.dll")
_NULL_HANDLE = object()
_IMPORT_LOCK = threading.Lock()
_DLL_LOCK = threading.Lock()
_DLL_HANDLES: list[Any] = []
_REGISTERED_DLL_DIRS: set[str] = set()


def _runtime_root(root_dir: Path | None) -> Path:
    base = root_dir or DEFAULT_AUDIO_ROOT
    return base / "runtime" / "fluidsynth"


def _normalize_path(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved)
    return result


def _add_path_if_exists(paths: list[Path], candidate: Path | None) -> None:
    if candidate is None:
        return
    try:
        if candidate.exists():
            paths.append(candidate)
    except OSError:
        return


def _search_root(root: Path, pattern: str) -> list[Path]:
    if not root.exists():
        return []
    try:
        return [match.parent for match in root.glob(pattern) if match.is_file()]
    except OSError:
        return []


def _candidate_windows_dirs(root_dir: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    runtime_root = _runtime_root(root_dir)
    _add_path_if_exists(candidates, runtime_root)
    _add_path_if_exists(candidates, runtime_root / "bin")
    candidates.extend(_search_root(runtime_root, "**/fluidsynth.exe"))
    for dll_glob in _WINDOWS_DLL_GLOBS:
        candidates.extend(_search_root(runtime_root, f"**/{dll_glob}"))

    for env_name in ("NNS_FLUIDSYNTH_BIN", "FLUIDSYNTH_BIN", "FLUIDSYNTH_HOME"):
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            env_path = Path(env_value)
            _add_path_if_exists(candidates, env_path)
            _add_path_if_exists(candidates, env_path / "bin")

    binary = shutil.which("fluidsynth")
    if binary:
        _add_path_if_exists(candidates, Path(binary).resolve().parent)

    for hint in _WINDOWS_BIN_HINTS:
        _add_path_if_exists(candidates, hint)

    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if local_app_data:
        winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        candidates.extend(_search_root(winget_root, "*FluidSynth*/**/fluidsynth.exe"))
        for dll_glob in _WINDOWS_DLL_GLOBS:
            candidates.extend(_search_root(winget_root, f"*FluidSynth*/**/{dll_glob}"))

    chocolatey_root = Path(os.getenv("ChocolateyInstall", r"C:\ProgramData\chocolatey")) / "lib" / "fluidsynth"
    candidates.extend(_search_root(chocolatey_root, "**/fluidsynth.exe"))
    for dll_glob in _WINDOWS_DLL_GLOBS:
        candidates.extend(_search_root(chocolatey_root, f"**/{dll_glob}"))

    scoop_root = Path.home() / "scoop" / "apps" / "fluidsynth" / "current"
    _add_path_if_exists(candidates, scoop_root)
    _add_path_if_exists(candidates, scoop_root / "bin")

    return _dedupe_paths(candidates)


def _find_windows_binary(root_dir: Path | None = None) -> Path | None:
    binary = shutil.which("fluidsynth")
    if binary:
        return Path(binary).resolve()

    for directory in _candidate_windows_dirs(root_dir):
        candidate = directory / "fluidsynth.exe"
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _find_windows_library(root_dir: Path | None = None) -> Path | None:
    for directory in _candidate_windows_dirs(root_dir):
        for dll_glob in _WINDOWS_DLL_GLOBS:
            try:
                matches = sorted(directory.glob(dll_glob))
            except OSError:
                continue
            for match in matches:
                if match.is_file():
                    return match.resolve()
    return None


def find_runtime_snapshot(root_dir: Path | None = None) -> dict[str, Any]:
    if os.name == "nt":
        binary_path = _find_windows_binary(root_dir)
        library_path = _find_windows_library(root_dir)
        bin_dirs: list[Path] = []
        if binary_path is not None:
            bin_dirs.append(binary_path.parent)
        if library_path is not None:
            bin_dirs.append(library_path.parent)
        bin_dirs.extend(_candidate_windows_dirs(root_dir))
        return {
            "runtime_ready": binary_path is not None or library_path is not None,
            "binary_path": str(binary_path) if binary_path is not None else None,
            "library_path": str(library_path) if library_path is not None else None,
            "bin_dirs": [str(path) for path in _dedupe_paths(bin_dirs)],
        }

    binary = shutil.which("fluidsynth")
    return {
        "runtime_ready": binary is not None,
        "binary_path": binary,
        "library_path": None,
        "bin_dirs": [],
    }


def _prepend_path(path: Path) -> None:
    current = os.environ.get("PATH", "")
    pieces = [piece for piece in current.split(os.pathsep) if piece]
    normalized = {_normalize_path(piece) for piece in pieces}
    if _normalize_path(path) in normalized:
        return
    os.environ["PATH"] = str(path) + (os.pathsep + current if current else "")


def _register_dll_directory(path: Path) -> None:
    if not hasattr(os, "add_dll_directory"):
        return
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    key = os.path.normcase(str(resolved))
    with _DLL_LOCK:
        if key in _REGISTERED_DLL_DIRS:
            return
        try:
            handle = os.add_dll_directory(str(resolved))
        except (FileNotFoundError, OSError):
            return
        _REGISTERED_DLL_DIRS.add(key)
        _DLL_HANDLES.append(handle)


def prepare_fluidsynth_environment(root_dir: Path | None = None) -> dict[str, Any]:
    snapshot = find_runtime_snapshot(root_dir)
    if os.name != "nt":
        return snapshot

    for directory_text in snapshot.get("bin_dirs", []):
        directory = Path(str(directory_text))
        _prepend_path(directory)
        _register_dll_directory(directory)
    return snapshot


@contextmanager
def _swallow_missing_add_dll_directory():
    if not hasattr(os, "add_dll_directory"):
        yield
        return

    original = os.add_dll_directory

    def safe_add_dll_directory(path: str) -> Any:
        try:
            return original(path)
        except FileNotFoundError:
            return _NULL_HANDLE

    os.add_dll_directory = safe_add_dll_directory  # type: ignore[assignment]
    try:
        yield
    finally:
        os.add_dll_directory = original  # type: ignore[assignment]


def import_fluidsynth_module(root_dir: Path | None = None) -> Any:
    prepare_fluidsynth_environment(root_dir)
    with _IMPORT_LOCK:
        existing = sys.modules.get("fluidsynth")
        if existing is not None and hasattr(existing, "Synth"):
            return existing
        sys.modules.pop("fluidsynth", None)
        with _swallow_missing_add_dll_directory():
            try:
                return importlib.import_module("fluidsynth")
            except Exception:
                sys.modules.pop("fluidsynth", None)
                raise
