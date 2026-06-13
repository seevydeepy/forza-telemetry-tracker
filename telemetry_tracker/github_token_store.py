"""Private GitHub release token storage.

The installed Windows app stores temporary private-repository update tokens in
Windows Credential Manager. Development builds can use the environment fallback
so no developer needs to configure Credential Manager just to test release
checks.
"""
from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from typing import Literal

GITHUB_TOKEN_ENV = "FORZA_TRACKER_GITHUB_TOKEN"
CREDENTIAL_TARGET = "Forza Telemetry Tracker GitHub Releases"

TokenSource = Literal["environment", "credential_manager"]


@dataclass(frozen=True)
class TokenStatus:
    configured: bool
    source: TokenSource | None = None
    storage_available: bool = True
    message: str | None = None


class TokenStorageUnavailable(RuntimeError):
    """Raised when credential-manager writes are requested off Windows."""


def _env_token() -> str | None:
    token = os.environ.get(GITHUB_TOKEN_ENV)
    if token and token.strip():
        return token.strip()
    return None


def _credential_manager_available() -> bool:
    return os.name == "nt"


if os.name == "nt":  # pragma: no cover - exercised through mocks on non-Windows CI
    from ctypes import wintypes

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
        _fields_ = [
            ("Keyword", wintypes.LPWSTR),
            ("Flags", wintypes.DWORD),
            ("ValueSize", wintypes.DWORD),
            ("Value", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTEW)),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    PCREDENTIALW = ctypes.POINTER(CREDENTIALW)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCREDENTIALW)]
    _advapi32.CredReadW.restype = wintypes.BOOL
    _advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    _advapi32.CredWriteW.restype = wintypes.BOOL
    _advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _advapi32.CredDeleteW.restype = wintypes.BOOL
    _advapi32.CredFree.argtypes = [ctypes.c_void_p]
    _advapi32.CredFree.restype = None
else:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168
    CREDENTIALW = object  # type: ignore[assignment]
    PCREDENTIALW = object  # type: ignore[assignment]
    _advapi32 = None


def read_windows_credential(target: str = CREDENTIAL_TARGET) -> str | None:
    if not _credential_manager_available():
        return None
    credential_ptr = ctypes.POINTER(CREDENTIALW)()
    success = _advapi32.CredReadW(
        target,
        CRED_TYPE_GENERIC,
        0,
        ctypes.byref(credential_ptr),
    )
    if not success:
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return None
        raise ctypes.WinError(error)
    try:
        credential = credential_ptr.contents
        if not credential.CredentialBlob or credential.CredentialBlobSize <= 0:
            return None
        blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return blob.decode("utf-16-le").rstrip("\x00") or None
    finally:
        _advapi32.CredFree(credential_ptr)


def write_windows_credential(token: str, target: str = CREDENTIAL_TARGET) -> None:
    if not _credential_manager_available():
        raise TokenStorageUnavailable("Windows Credential Manager is only available on Windows")
    clean_token = token.strip()
    if not clean_token:
        raise ValueError("token must not be empty")
    blob = clean_token.encode("utf-16-le")
    blob_buffer = ctypes.create_string_buffer(blob)
    credential = CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "GitHub fine-grained PAT"
    success = _advapi32.CredWriteW(ctypes.byref(credential), 0)
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())


def delete_windows_credential(target: str = CREDENTIAL_TARGET) -> None:
    if not _credential_manager_available():
        raise TokenStorageUnavailable("Windows Credential Manager is only available on Windows")
    success = _advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0)
    if not success:
        error = ctypes.get_last_error()
        if error != ERROR_NOT_FOUND:
            raise ctypes.WinError(error)


class GitHubTokenStore:
    """Read/write GitHub tokens without ever exposing token values in status."""

    def read_token(self) -> str | None:
        token = _env_token()
        if token is not None:
            return token
        return read_windows_credential()

    def status(self) -> TokenStatus:
        if _env_token() is not None:
            return TokenStatus(configured=True, source="environment", storage_available=_credential_manager_available())
        token = read_windows_credential()
        if token:
            return TokenStatus(configured=True, source="credential_manager", storage_available=_credential_manager_available())
        return TokenStatus(configured=False, storage_available=_credential_manager_available())

    def save_token(self, token: str) -> TokenStatus:
        write_windows_credential(token)
        return self.status()

    def clear_token(self) -> TokenStatus:
        delete_windows_credential()
        return self.status()
