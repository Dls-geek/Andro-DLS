"""
Resolve external binaries (ADB, Metasploit, scrcpy, nmap) the same way as startup:
PATH via shutil.which, plus Windows local copies next to the project (README).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from modules.config import AppConfig


def _which(name: str) -> str | None:
    return shutil.which(name)


def find_adb_exe(operating_system: str) -> str | None:
    w = _which("adb")
    if w:
        return w
    # Bundled-copy fallback (portable setup): check repo-local adb on every
    # platform, not just Windows (README documents local copies on Windows;
    # the repo also ships a Linux adb binary).
    root = Path(__file__).resolve().parent.parent
    names = ("adb.exe", "adb") if operating_system == "Windows" else ("adb",)
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def find_msfvenom() -> str | None:
    return _which("msfvenom")


def find_msfconsole() -> str | None:
    return _which("msfconsole")


def find_scrcpy(operating_system: str) -> str | None:
    # Prefer the bundled scrcpy next to the repo FIRST: it is a pinned modern
    # build (3.3.3, Sep 2025) whose server supports Android 14/15. A system
    # scrcpy on PATH may be an old distro package (e.g. 1.25 on Ubuntu 24.04)
    # whose server crashes on Android 13+ (ClipboardManager
    # NoSuchMethodException: addPrimaryClipChangedListener) — mirror then dies
    # instantly. Fall back to PATH only when no bundled copy exists.
    root = Path(__file__).resolve().parent.parent
    names = ("scrcpy.exe", "scrcpy") if operating_system == "Windows" else ("scrcpy",)
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return str(candidate.resolve())
    w = _which("scrcpy") or (_which("scrcpy.exe") if operating_system == "Windows" else None)
    if w:
        return w
    return None


def find_nmap() -> str | None:
    return _which("nmap")


def resolve_external_tools(config: AppConfig) -> None:
    config.adb_path = find_adb_exe(config.operating_system)
    config.msfvenom_path = find_msfvenom()
    config.msfconsole_path = find_msfconsole()
    config.scrcpy_path = find_scrcpy(config.operating_system)
    config.nmap_path = find_nmap()


def require_adb(config: AppConfig) -> bool:
    if config.adb_path:
        return True
    from modules.console import print_error

    print_error(
        "ADB is not installed or not on PATH. "
        "Install Android SDK Platform Tools (or place adb next to this program on Windows)."
    )
    return False


def require_scrcpy(config: AppConfig) -> bool:
    if config.scrcpy_path:
        return True
    from modules.console import print_error

    print_error("Scrcpy is not installed or not on PATH. Install scrcpy and try again.")
    return False


def require_nmap(config: AppConfig) -> bool:
    if config.nmap_path:
        return True
    from modules.console import print_error

    print_error("Nmap is not installed or not on PATH. Install nmap and try again.")
    return False


def require_metasploit(config: AppConfig) -> bool:
    if config.msfvenom_path and config.msfconsole_path:
        return True
    from modules.console import print_error

    print_error(
        "Metasploit-Framework (msfvenom and msfconsole) not found on PATH. "
        "Install Metasploit and try again."
    )
    return False


def scrcpy_argv(config: AppConfig, args: list[str]) -> list[str]:
    """Build argv for subprocess; caller must ensure require_scrcpy(config) first."""
    return [config.scrcpy_path or "scrcpy"] + args
