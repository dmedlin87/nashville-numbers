from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import zipfile as zipfile_module
from unittest.mock import patch

import pytest

from nashville_numbers.audio.errors import AudioInstallError
from nashville_numbers.audio.installer import DEFAULT_PACK, DefaultPackInstaller, RuntimeAsset, RuntimeInstaller


class TestRuntimeInstallerStatus:
    @staticmethod
    def _snapshot(runtime_ready: bool, runtime_path: str | None = None, library_path: str | None = None) -> dict[str, object]:
        return {
            "runtime_ready": runtime_ready,
            "binary_path": runtime_path,
            "library_path": library_path,
            "bin_dirs": [],
        }

    def test_status_returns_dict_with_expected_keys(self) -> None:
        installer = RuntimeInstaller()
        with patch(
            "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
            return_value=self._snapshot(False),
        ):
            result = installer.status()
        assert "runtime_binary" in result
        assert "python_binding" in result
        assert isinstance(result["runtime_binary"], bool)
        assert isinstance(result["python_binding"], bool)

    def test_status_runtime_binary_false_when_not_on_path(self) -> None:
        installer = RuntimeInstaller()
        with patch(
            "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
            return_value=self._snapshot(False),
        ):
            result = installer.status()
        assert result["runtime_binary"] is False

    def test_status_runtime_binary_true_when_on_path(self) -> None:
        installer = RuntimeInstaller()
        with patch(
            "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
            return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
        ):
            result = installer.status()
        assert result["runtime_binary"] is True

    def test_status_python_binding_false_when_import_fails(self) -> None:
        installer = RuntimeInstaller()
        with patch.object(installer, "_check_python_binding", return_value=False):
            result = installer.status()
        assert result["python_binding"] is False

    def test_status_python_binding_true_when_import_succeeds(self) -> None:
        installer = RuntimeInstaller()
        with patch.object(installer, "_check_python_binding", return_value=True):
            result = installer.status()
        assert result["python_binding"] is True

    def test_status_detects_portable_runtime_library(self, tmp_path) -> None:
        installer = RuntimeInstaller(root_dir=tmp_path)
        runtime_dir = tmp_path / "runtime" / "fluidsynth" / "portable" / "bin"
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "libfluidsynth-3.dll").write_bytes(b"dll")

        with (
            patch("nashville_numbers.audio.runtime_support.os.name", "nt"),
            patch("nashville_numbers.audio.runtime_support._candidate_windows_dirs", return_value=[runtime_dir]),
            patch("nashville_numbers.audio.runtime_support.shutil.which", return_value=None),
            patch("nashville_numbers.audio.runtime_support._prepend_path"),
            patch("nashville_numbers.audio.runtime_support._register_dll_directory"),
            patch.object(installer, "_check_python_binding", return_value=False),
        ):
            result = installer.status()

        assert result["runtime_binary"] is True
        assert result["library_path"] == str(runtime_dir / "libfluidsynth-3.dll")

    def test_check_python_binding_ignores_missing_add_dll_directory(self, monkeypatch, tmp_path) -> None:
        if not hasattr(os, "add_dll_directory"):
            pytest.skip("Windows-specific import behavior")

        installer = RuntimeInstaller(root_dir=tmp_path)
        module_dir = tmp_path / "modules"
        module_dir.mkdir()
        (module_dir / "fluidsynth.py").write_text(
            "import os\n"
            "os.add_dll_directory(r'C:\\tools\\fluidsynth\\bin')\n"
            "class Synth:\n"
            "    pass\n",
            encoding="utf-8",
        )

        monkeypatch.syspath_prepend(str(module_dir))
        monkeypatch.delitem(sys.modules, "fluidsynth", raising=False)

        try:
            assert installer._check_python_binding() is True
        finally:
            monkeypatch.delitem(sys.modules, "fluidsynth", raising=False)


class TestRuntimeInstallerInstall:
    def _make_installer(self) -> RuntimeInstaller:
        return RuntimeInstaller()

    @staticmethod
    def _snapshot(runtime_ready: bool, runtime_path: str | None = None, library_path: str | None = None) -> dict[str, object]:
        return {
            "runtime_ready": runtime_ready,
            "binary_path": runtime_path,
            "library_path": library_path,
            "bin_dirs": [],
        }

    def test_install_returns_ready_when_both_succeed(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
            ),
            patch.object(installer, "_check_python_binding", return_value=True),
        ):
            result = installer.install()
        assert result["ready"] is True
        assert result["runtime_binary"] is True
        assert result["python_binding"] is True
        assert "message" in result

    def test_install_skips_runtime_install_when_binary_already_present(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
            ),
            patch.object(installer, "_install_runtime", return_value=False) as mock_install,
            patch.object(installer, "_check_python_binding", return_value=True),
        ):
            installer.install()
        mock_install.assert_not_called()

    def test_install_attempts_runtime_install_when_binary_missing(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                side_effect=[
                    self._snapshot(False),
                    self._snapshot(True, runtime_path="/portable/fluidsynth.exe"),
                ],
            ),
            patch.object(installer, "_install_runtime", return_value=True) as mock_install,
            patch.object(installer, "_check_python_binding", return_value=True),
            patch.object(installer, "_patch_windows_path"),
        ):
            installer.install()
        mock_install.assert_called_once()

    def test_install_calls_pip_when_binding_missing(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
            ),
            patch.object(installer, "_check_python_binding", return_value=False),
            patch.object(installer, "_install_python_binding", return_value=True) as mock_pip,
        ):
            installer.install()
        mock_pip.assert_called_once()

    def test_install_returns_partial_result_when_runtime_fails(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                side_effect=[self._snapshot(False), self._snapshot(False)],
            ),
            patch.object(installer, "_install_runtime", return_value=False),
            patch.object(installer, "_check_python_binding", return_value=True),
        ):
            result = installer.install()
        assert result["ready"] is False
        assert result["runtime_binary"] is False
        assert result["python_binding"] is True

    def test_install_returns_partial_result_when_binding_fails(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
            ),
            patch.object(installer, "_check_python_binding", return_value=False),
            patch.object(installer, "_install_python_binding", return_value=False),
        ):
            result = installer.install()
        assert result["ready"] is False
        assert result["runtime_binary"] is True
        assert result["python_binding"] is False

    def test_install_message_ready(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
            ),
            patch.object(installer, "_check_python_binding", return_value=True),
        ):
            result = installer.install()
        assert "ready" in result["message"].lower()

    def test_install_message_when_both_fail(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                side_effect=[self._snapshot(False), self._snapshot(False)],
            ),
            patch.object(installer, "_install_runtime", return_value=False),
            patch.object(installer, "_check_python_binding", return_value=False),
            patch.object(installer, "_install_python_binding", return_value=False),
        ):
            result = installer.install()
        assert result["ready"] is False
        assert len(result["message"]) > 0

    def test_install_rechecks_binding_after_pip_install(self) -> None:
        installer = self._make_installer()
        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
            ),
            patch.object(installer, "_check_python_binding", side_effect=[False, False]),
            patch.object(installer, "_install_python_binding", return_value=True) as mock_pip,
        ):
            result = installer.install()

        mock_pip.assert_called_once()
        assert result["python_binding"] is False
        assert result["ready"] is False

    def test_on_progress_called_with_stages(self) -> None:
        installer = self._make_installer()
        calls: list[tuple[int, str]] = []

        def cb(pct: int, stage: str) -> None:
            calls.append((pct, stage))

        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
            ),
            patch.object(installer, "_check_python_binding", return_value=True),
        ):
            installer.install(on_progress=cb)

        assert len(calls) >= 2
        pcts = [c[0] for c in calls]
        assert pcts[0] < pcts[-1]
        assert pcts[-1] == 100

    def test_on_progress_exception_is_swallowed(self) -> None:
        installer = self._make_installer()

        def bad_cb(pct: int, stage: str) -> None:
            raise RuntimeError("callback exploded")

        with (
            patch(
                "nashville_numbers.audio.installer.prepare_fluidsynth_environment",
                return_value=self._snapshot(True, runtime_path="/usr/bin/fluidsynth"),
            ),
            patch.object(installer, "_check_python_binding", return_value=True),
        ):
            result = installer.install(on_progress=bad_cb)
        assert result["ready"] is True


class TestRuntimeInstallerTryCommand:
    def test_try_command_returns_true_on_zero_exit(self) -> None:
        installer = RuntimeInstaller()
        completed = subprocess.CompletedProcess(args=[], returncode=0)
        with patch("subprocess.run", return_value=completed):
            assert installer._try_command(["echo", "hi"]) is True

    def test_try_command_returns_false_on_nonzero_exit(self) -> None:
        installer = RuntimeInstaller()
        completed = subprocess.CompletedProcess(args=[], returncode=1)
        with patch("subprocess.run", return_value=completed):
            assert installer._try_command(["false"]) is False

    def test_try_command_returns_false_on_timeout(self) -> None:
        installer = RuntimeInstaller()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=1)):
            assert installer._try_command(["slow"]) is False

    def test_try_command_returns_false_on_file_not_found(self) -> None:
        installer = RuntimeInstaller()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert installer._try_command(["missing_exe"]) is False

    def test_install_python_binding_uses_current_interpreter(self) -> None:
        installer = RuntimeInstaller()
        captured: list[list[str]] = []

        def fake_try_command(cmd: list[str]) -> bool:
            captured.append(cmd)
            return True

        with patch.object(installer, "_try_command", side_effect=fake_try_command):
            installer._install_python_binding()

        assert captured[0][0] == sys.executable
        assert "pip" in captured[0]
        assert any("pyfluidsynth" in arg for arg in captured[0])


# ---------------------------------------------------------------------------
# DefaultPackInstaller
# ---------------------------------------------------------------------------

def _make_zip(contents: dict[str, bytes]) -> bytes:
    """Create an in-memory zip with the given filename→bytes mapping."""
    buf = io.BytesIO()
    with zipfile_module.ZipFile(buf, "w") as zf:
        for name, data in contents.items():
            zf.writestr(name, data)
    return buf.getvalue()


class TestDefaultPackInstallerStatus:
    def test_status_not_installed(self, tmp_path) -> None:
        installer = DefaultPackInstaller(tmp_path)
        result = installer.status()
        assert result["id"] == DEFAULT_PACK.id
        assert result["installed"] is False
        assert result["path"] is None

    def test_status_installed_direct(self, tmp_path) -> None:
        pack_root = tmp_path / "packs" / DEFAULT_PACK.id
        pack_root.mkdir(parents=True)
        sf2 = pack_root / DEFAULT_PACK.soundfont_file
        sf2.write_bytes(b"fake")
        installer = DefaultPackInstaller(tmp_path)
        result = installer.status()
        assert result["installed"] is True
        assert result["path"] == str(sf2)

    def test_status_installed_nested(self, tmp_path) -> None:
        """_find_soundfont falls back to rglob when not at root."""
        pack_root = tmp_path / "packs" / DEFAULT_PACK.id
        nested = pack_root / "sub"
        nested.mkdir(parents=True)
        sf2 = nested / DEFAULT_PACK.soundfont_file
        sf2.write_bytes(b"fake")
        installer = DefaultPackInstaller(tmp_path)
        result = installer.status()
        assert result["installed"] is True

    def test_status_pack_root_missing(self, tmp_path) -> None:
        installer = DefaultPackInstaller(tmp_path)
        result = installer.status()
        assert result["installed"] is False


class TestDefaultPackInstallerInstallDefault:
    def test_returns_existing_soundfont_without_downloading(self, tmp_path) -> None:
        pack_root = tmp_path / "packs" / DEFAULT_PACK.id
        pack_root.mkdir(parents=True)
        sf2 = pack_root / DEFAULT_PACK.soundfont_file
        sf2.write_bytes(b"fake")
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen") as mock_urlopen:
            result = installer.install_default()
        mock_urlopen.assert_not_called()
        assert result == sf2

    def test_writes_notice_for_existing_soundfont(self, tmp_path) -> None:
        pack_root = tmp_path / "packs" / DEFAULT_PACK.id
        pack_root.mkdir(parents=True)
        (pack_root / DEFAULT_PACK.soundfont_file).write_bytes(b"fake")
        installer = DefaultPackInstaller(tmp_path)
        installer.install_default()
        notice = pack_root / "THIRD_PARTY_NOTICE.txt"
        assert notice.exists()
        assert DEFAULT_PACK.notice_text in notice.read_text(encoding="utf-8")

    def test_downloads_extracts_and_returns_soundfont(self, tmp_path) -> None:
        zip_bytes = _make_zip({DEFAULT_PACK.soundfont_file: b"sf2data"})
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(zip_bytes)):
            result = installer.install_default()
        assert result.name == DEFAULT_PACK.soundfont_file
        assert result.exists()

    def test_writes_pack_json_after_download(self, tmp_path) -> None:
        zip_bytes = _make_zip({DEFAULT_PACK.soundfont_file: b"sf2data"})
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(zip_bytes)):
            installer.install_default()
        pack_json = tmp_path / "packs" / DEFAULT_PACK.id / "pack.json"
        assert pack_json.exists()
        data = json.loads(pack_json.read_text(encoding="utf-8"))
        assert data["id"] == DEFAULT_PACK.id

    def test_raises_audio_install_error_on_url_error(self, tmp_path) -> None:
        from urllib.error import URLError
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", side_effect=URLError("network down")):
            with pytest.raises(AudioInstallError) as exc_info:
                installer.install_default()
        assert exc_info.value.code == "network_unavailable"

    def test_raises_audio_install_error_on_os_error_write(self, tmp_path) -> None:
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(b"data")):
            with patch("nashville_numbers.audio.installer.shutil.copyfileobj", side_effect=OSError("disk full")):
                with pytest.raises(AudioInstallError) as exc_info:
                    installer.install_default()
        assert exc_info.value.code == "download_failed"

    def test_raises_on_bad_zip(self, tmp_path) -> None:
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(b"not a zip")):
            with pytest.raises(AudioInstallError) as exc_info:
                installer.install_default()
        assert exc_info.value.code == "invalid_pack"

    def test_raises_on_zip_slip(self, tmp_path) -> None:
        """Members whose resolved path escapes pack_root must be rejected."""
        buf = io.BytesIO()
        with zipfile_module.ZipFile(buf, "w") as zf:
            zf.writestr("../../evil.txt", b"pwned")
        zip_bytes = buf.getvalue()
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(zip_bytes)):
            with pytest.raises(AudioInstallError) as exc_info:
                installer.install_default()
        assert exc_info.value.code == "invalid_pack"

    def test_raises_when_soundfont_missing_from_archive(self, tmp_path) -> None:
        zip_bytes = _make_zip({"other_file.txt": b"irrelevant"})
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(zip_bytes)):
            with pytest.raises(AudioInstallError) as exc_info:
                installer.install_default()
        assert exc_info.value.code == "invalid_pack"
        assert DEFAULT_PACK.soundfont_file in str(exc_info.value)

    def test_cleans_up_archive_on_bad_zip(self, tmp_path) -> None:
        """archive_path must be removed even when extraction raises."""
        installer = DefaultPackInstaller(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(b"not a zip")):
            with pytest.raises(AudioInstallError):
                installer.install_default()
        assert not any(installer.temp_root.glob("*.zip"))


# ---------------------------------------------------------------------------
# RuntimeInstaller internals — _find_windows_asset / _install_windows_portable
# ---------------------------------------------------------------------------

class TestFindWindowsAsset:
    def _installer(self, tmp_path) -> RuntimeInstaller:
        return RuntimeInstaller(root_dir=tmp_path)

    def _releases_payload(self, tag: str, asset_name: str, url: str) -> list:
        return [{"tag_name": tag, "assets": [{"name": asset_name, "browser_download_url": url}]}]

    def test_finds_x64_cpp11_asset(self, tmp_path) -> None:
        arch = "x64" if sys.maxsize > 2**32 else "x86"
        asset_name = f"fluidsynth-2.3.4-win10-{arch}-cpp11.zip"
        payload = self._releases_payload("v2.3.4", asset_name, "https://example.com/fs.zip")
        installer = self._installer(tmp_path)
        with patch(
            "nashville_numbers.audio.installer.urlopen",
            return_value=io.BytesIO(json.dumps(payload).encode()),
        ):
            asset = installer._find_windows_asset()
        assert asset.name == asset_name
        assert asset.tag_name == "v2.3.4"
        assert asset.download_url == "https://example.com/fs.zip"

    def test_raises_when_no_compatible_asset(self, tmp_path) -> None:
        payload = [{"tag_name": "v1.0.0", "assets": [{"name": "linux-x64.tar.gz", "browser_download_url": "https://example.com/x.tar.gz"}]}]
        installer = self._installer(tmp_path)
        with patch(
            "nashville_numbers.audio.installer.urlopen",
            return_value=io.BytesIO(json.dumps(payload).encode()),
        ):
            with pytest.raises(AudioInstallError) as exc_info:
                installer._find_windows_asset()
        assert exc_info.value.code == "runtime_lookup_failed"

    def test_raises_when_payload_is_not_list(self, tmp_path) -> None:
        installer = self._installer(tmp_path)
        with patch(
            "nashville_numbers.audio.installer.urlopen",
            return_value=io.BytesIO(json.dumps({"error": "bad"}).encode()),
        ):
            with pytest.raises(AudioInstallError) as exc_info:
                installer._find_windows_asset()
        assert exc_info.value.code == "runtime_lookup_failed"

    def test_raises_on_url_error(self, tmp_path) -> None:
        from urllib.error import URLError
        installer = self._installer(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", side_effect=URLError("no network")):
            with pytest.raises(AudioInstallError) as exc_info:
                installer._find_windows_asset()
        assert exc_info.value.code == "runtime_lookup_failed"

    def test_raises_on_invalid_json(self, tmp_path) -> None:
        installer = self._installer(tmp_path)
        with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(b"not json{")):
            with pytest.raises(AudioInstallError) as exc_info:
                installer._find_windows_asset()
        assert exc_info.value.code == "runtime_lookup_failed"

    def test_skips_non_dict_releases(self, tmp_path) -> None:
        arch = "x64" if sys.maxsize > 2**32 else "x86"
        asset_name = f"fluidsynth-2.3.4-win10-{arch}-cpp11.zip"
        payload = [
            "not-a-dict",
            {"tag_name": "v2.3.4", "assets": [{"name": asset_name, "browser_download_url": "https://example.com/fs.zip"}]},
        ]
        installer = self._installer(tmp_path)
        with patch(
            "nashville_numbers.audio.installer.urlopen",
            return_value=io.BytesIO(json.dumps(payload).encode()),
        ):
            asset = installer._find_windows_asset()
        assert asset.name == asset_name


class TestInstallWindowsPortable:
    def _installer(self, tmp_path) -> RuntimeInstaller:
        return RuntimeInstaller(root_dir=tmp_path)

    def _fake_asset(self) -> RuntimeAsset:
        return RuntimeAsset(tag_name="v2.3.4", name="fluidsynth-win10-x64.zip", download_url="https://example.com/fs.zip")

    def _zip_with_dll(self) -> bytes:
        return _make_zip({"bin/libfluidsynth-3.dll": b"dll"})

    def test_returns_false_when_find_asset_fails(self, tmp_path) -> None:
        installer = self._installer(tmp_path)
        with patch.object(installer, "_find_windows_asset", side_effect=AudioInstallError("runtime_lookup_failed", "no asset")):
            result = installer._install_windows_portable()
        assert result is False
        assert installer._last_runtime_error is not None

    def test_returns_false_on_download_error(self, tmp_path) -> None:
        from urllib.error import URLError
        installer = self._installer(tmp_path)
        with patch.object(installer, "_find_windows_asset", return_value=self._fake_asset()):
            with patch("nashville_numbers.audio.installer.urlopen", side_effect=URLError("down")):
                result = installer._install_windows_portable()
        assert result is False
        assert installer._last_runtime_error is not None

    def test_returns_false_on_bad_zip(self, tmp_path) -> None:
        installer = self._installer(tmp_path)
        with patch.object(installer, "_find_windows_asset", return_value=self._fake_asset()):
            with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(b"not a zip")):
                result = installer._install_windows_portable()
        assert result is False

    def test_returns_false_when_no_binary_or_dll(self, tmp_path) -> None:
        zip_bytes = _make_zip({"readme.txt": b"hi"})
        installer = self._installer(tmp_path)
        with patch.object(installer, "_find_windows_asset", return_value=self._fake_asset()):
            with patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(zip_bytes)):
                result = installer._install_windows_portable()
        assert result is False
        assert "did not contain" in (installer._last_runtime_error or "")

    def test_calls_on_progress_with_download_stage(self, tmp_path) -> None:
        installer = self._installer(tmp_path)
        calls: list[tuple[int, str]] = []
        with (
            patch.object(installer, "_find_windows_asset", return_value=self._fake_asset()),
            patch("nashville_numbers.audio.installer.urlopen", return_value=io.BytesIO(b"not a zip")),
        ):
            installer._install_windows_portable(on_progress=lambda p, s: calls.append((p, s)))
        assert any("Download" in s or "download" in s.lower() for _, s in calls)

    def test_extract_zip_raises_on_zip_slip(self, tmp_path) -> None:
        """_extract_zip must reject paths that escape the destination."""
        installer = self._installer(tmp_path)
        buf = io.BytesIO()
        with zipfile_module.ZipFile(buf, "w") as zf:
            zf.writestr("../../evil.txt", b"pwned")
        buf.seek(0)
        dest = tmp_path / "dest"
        dest.mkdir()
        with zipfile_module.ZipFile(buf, "r") as zf:
            with pytest.raises(AudioInstallError) as exc_info:
                installer._extract_zip(zf, dest)
        assert exc_info.value.code == "invalid_pack"
