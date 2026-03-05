"""Audio subsystem exceptions."""

from __future__ import annotations


class AudioError(RuntimeError):
    """Base audio exception."""


class AudioUnavailableError(AudioError):
    """Raised when HQ audio cannot be used in the current environment."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AudioInstallError(AudioError):
    """Raised when installation of a sound pack fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

