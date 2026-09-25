"""Watchdog menu (CLI option 66) — control the dls-keeper 24/7 daemon.

The keeper runs OUTSIDE this CLI as a systemd user service, so the tunnel +
shell listener stay up even when Andro-DLS is closed. This menu is just
a friendly remote control: status / start / stop / attach / wake / logs.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from modules.config import AppConfig
from modules.console import console, ask, print_error, print_success, print_warning

REPO = Path(__file__).resolve().parent.parent
KEEPER = REPO / "modules" / "keeper.py"
UNIT = Path.home() / ".config/systemd/user/dls-keeper.service"
INSTALLER = REPO / "watchdog" / "install.sh"


def _py() -> str:
    return sys.executable or "python3"


def _systemctl(*args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True, text=True, timeout=20,
        )
        return r.returncode, (r.stdout or r.stderr or "").strip()
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def _installed() -> bool:
    return UNIT.exists()


MENU = """
[bold yellow]── WATCHDOG / 24-7 KEEPER ──────────────────────────────────[/bold yellow]
[white]1.[/white] Status            [white]2.[/white] Attach to live session
[white]3.[/white] Wake payload       [white]4.[/white] Stop keeper
[white]5.[/white] Start keeper       [white]6.[/white] Restart keeper
[white]7.[/white] Live logs          [white]8.[/white] Install systemd unit (+linger)
[white]0.[/white] Back

[dim]keeper = permanent portmap tunnel + always-on listener; phone reconnects
by itself and the session waits for you — no rebuild, no expiry.[/dim]
"""


def _status() -> None:
    r = subprocess.run(
        [_py(), str(KEEPER), "status"], capture_output=True, text=True, timeout=15
    )
    out = (r.stdout or "").strip()
    if out:
        print(out)
    else:
        print_error("cannot reach keeper (not running?)")
    if not _installed():
        print_warning("\nsystemd unit NOT installed yet — option 8 to install (boot-survival)")


def watchdog_menu(config: AppConfig) -> None:
    while True:
        print(MENU)
        choice = ask("[red]\\[Watchdog][/red] > ").strip()
        if choice in ("0", "", "b", "back"):
            return
        elif choice == "1":
            _status()
        elif choice == "2":
            try:
                subprocess.run([_py(), str(KEEPER), "attach"])
            except KeyboardInterrupt:
                pass
        elif choice == "3":
            r = subprocess.run([_py(), str(KEEPER), "wake"], capture_output=True, text=True)
            print((r.stdout or "wake sent").strip())
        elif choice == "4":
            rc, out = _systemctl("stop", "dls-keeper.service")
            if rc == 0:
                print_success("keeper stopped (systemd)")
            else:
                r = subprocess.run([_py(), str(KEEPER), "stop"], capture_output=True, text=True)
                print((r.stdout or "stopped").strip())
        elif choice == "5":
            if not _installed():
                print_warning("unit not installed — installing first...")
                _install()
            rc, out = _systemctl("start", "dls-keeper.service")
            print_success("keeper started ✓") if rc == 0 else print_error(f"start failed:\n{out}")
        elif choice == "6":
            rc, out = _systemctl("restart", "dls-keeper.service")
            print_success("keeper restarted ✓") if rc == 0 else print_error(f"restart failed:\n{out}")
        elif choice == "7":
            try:
                subprocess.run(["journalctl", "--user", "-u", "dls-keeper", "-f", "-n", "50"])
            except KeyboardInterrupt:
                pass
        elif choice == "8":
            _install()


def _install() -> None:
    if not INSTALLER.exists():
        print_error(f"installer missing: {INSTALLER}")
        return
    print("[dim]running watchdog/install.sh ...[/dim]")
    try:
        r = subprocess.run(["bash", str(INSTALLER)], timeout=120)
    except subprocess.TimeoutExpired:
        print_error("installer timed out")
        return
    if r.returncode != 0:
        print_error("installer failed — run manually:")
        print(f"  bash {INSTALLER}")
