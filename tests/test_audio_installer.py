from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from nashville_numbers.audio.installer import RuntimeInstaller


class TestRuntimeInstallerStatus:
    def test_status_returns_dict_with_expected_keys(self) -> None:
        installer = RuntimeInstaller()
        result = installer.status()
        assert "runtime_binary" in result
        assert "python_binding" in result
        assert isinstance(result["runtime_binary"], bool)
        assert isinstance(result["python_binding"], bool)

    def test_status_runtime_binary_false_when_not_on_path(self) -> None:
        installer = RuntimeInstaller()
        with patch("shutil.which", return_value=None):
            result = installer.status()
        assert result["runtime_binary"] is False

    def test_status_runtime_binary_true_when_on_path(self) -> None:
        installer = RuntimeInstaller()
        with patch("shutil.which", return_value="/usr/bin/fluidsynth"):
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


class TestRuntimeInstallerInstall:
    def _make_installer(self) -> RuntimeInstaller:
        return RuntimeInstaller()

    def test_install_returns_ready_when_both_succeed(self) -> None:
        installer = self._make_installer()
        with (
            patch("shutil.which", return_value="/usr/bin/fluidsynth"),
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
            patch("shutil.which", return_value="/usr/bin/fluidsynth"),
            patch.object(installer, "_install_runtime", return_value=False) as mock_install,
            patch.object(installer, "_check_python_binding", return_value=True),
        ):
            installer.install()
        mock_install.assert_not_called()

    def test_install_attempts_runtime_install_when_binary_missing(self) -> None:
        installer = self._make_installer()
        with (
            patch("shutil.which", return_value=None),
            patch.object(installer, "_install_runtime", return_value=True) as mock_install,
            patch.object(installer, "_check_python_binding", return_value=True),
            patch.object(installer, "_patch_windows_path"),
        ):
            installer.install()
        mock_install.assert_called_once()

    def test_install_calls_pip_when_binding_missing(self) -> None:
        installer = self._make_installer()
        with (
            patch("shutil.which", return_value="/usr/bin/fluidsynth"),
            patch.object(installer, "_check_python_binding", return_value=False),
            patch.object(installer, "_install_python_binding", return_value=True) as mock_pip,
        ):
            installer.install()
        mock_pip.assert_called_once()

    def test_install_returns_partial_result_when_runtime_fails(self) -> None:
        installer = self._make_installer()
        with (
            patch("shutil.which", return_value=None),
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
            patch("shutil.which", return_value="/usr/bin/fluidsynth"),
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
            patch("shutil.which", return_value="/usr/bin/fluidsynth"),
            patch.object(installer, "_check_python_binding", return_value=True),
        ):
            result = installer.install()
        assert "ready" in result["message"].lower()

    def test_install_message_when_both_fail(self) -> None:
        installer = self._make_installer()
        with (
            patch("shutil.which", return_value=None),
            patch.object(installer, "_install_runtime", return_value=False),
            patch.object(installer, "_check_python_binding", return_value=False),
            patch.object(installer, "_install_python_binding", return_value=False),
        ):
            result = installer.install()
        assert result["ready"] is False
        assert len(result["message"]) > 0

    def test_on_progress_called_with_stages(self) -> None:
        installer = self._make_installer()
        calls: list[tuple[int, str]] = []

        def cb(pct: int, stage: str) -> None:
            calls.append((pct, stage))

        with (
            patch("shutil.which", return_value="/usr/bin/fluidsynth"),
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
            patch("shutil.which", return_value="/usr/bin/fluidsynth"),
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
