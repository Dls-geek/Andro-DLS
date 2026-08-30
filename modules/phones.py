"""Setup Phones (CLI 68) — per-device portmap profiles for the fleet.

Each phone gets its own profile: name, adb serial/IP, portmap public port and
local port. Choosing a profile rewrites portmap.json so Full Access / Re-Access
target that phone. Profiles stored in .payload-build/phones.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from modules.config import AppConfig
from modules.console import console, ask, print_error, print_success, print_warning

ROOT = Path(__file__).resolve().parent.parent
PHONES = ROOT / ".payload-build" / "phones.json"
PORTMAP = ROOT / ".payload-build" / "portmap.json"


def load_phones() -> list[dict]:
    try:
        return json.loads(PHONES.read_text())
    except Exception:
        return []


def save_phones(phones: list[dict]) -> None:
    PHONES.parent.mkdir(parents=True, exist_ok=True)
    PHONES.write_text(json.dumps(phones, indent=2))


def _select_index(phones: list[dict], title: str) -> int | None:
    for i, p in enumerate(phones, 1):
        print(f"  [white]{i}.[/white] [green]{p['name']}[/green]  "
              f"{(p.get('serial') or p.get('ip') or '?')}  →  {p.get('public_port', '?')}")
    choice = ask(f"[cyan]{title}[/cyan] > ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(phones)):
        print_error("invalid selection")
        return None
    return int(choice) - 1


def setup_phones(config: AppConfig) -> None:
    console = _console()
    console.print("\n[bold cyan]▸ SETUP PHONES[/bold cyan]  multi-device profiles\n")

    while True:
        phones = load_phones()
        if phones:
            console.print("[dim]Existing profiles:[/dim]")
            for i, p in enumerate(phones, 1):
                console.print(f"  {i}. {p['name']} — {p.get('serial','?')} — pub {p.get('public_port','?')}")
            console.print("  [yellow]A)[/yellow] add new    [yellow]S)[/yellow] select/activate    [yellow]D)[/yellow] delete    [yellow]Q)[/yellow] back")
            choice = ask("[prompt]> [/prompt]").strip().lower()
        else:
            console.print("[dim]no profiles yet — add your first phone:[/dim]")
            choice = "a"

        if choice in ("q", ""):
            return
        if choice == "a":
            name = ask("[cyan]Phone name[/cyan] [dim](e.g. Infinix-HOT50)[/dim]> ").strip()
            serial = ask("[cyan]Serial / adb id[/cyan] [dim](Enter=auto-detect)[/dim]> ").strip()
            pub_port = ask("[cyan]Portmap public port[/cyan] [dim](the port for THIS phone)[/dim]> ").strip()
            local_port = ask("[cyan]Local listener port[/cyan] [dim](Enter=4444)[/dim]> ").strip() or "4444"
            if not name or not pub_port:
                print_error("name + public port required")
                continue
            phones = load_phones()
            phones.append({
                "name": name, "serial": serial, "public_port": pub_port,
                "local_port": local_port, "active": False,
            })
            save_phones(phones)
            print_success(f"added: {name} (pub {pub_port}, local {local_port})")
            continue
        if choice == "s":
            idx = _select_index(phones, "activate which phone")
            if idx is None:
                continue
            p = phones[idx]
            # rewrite portmap.json for this phone
            try:
                cfg = json.loads(PORTMAP.read_text()) if PORTMAP.exists() else {}
            except Exception:
                cfg = {}
            cfg.update({
                "public_port": p["public_port"],
                "local_port": p["local_port"],
            })
            if p.get("serial"):
                cfg["dial_host"] = cfg.get("dial_host", "")
            PORTMAP.write_text(json.dumps(cfg, indent=2))
            for x in phones:
                x["active"] = False
            phones[idx]["active"] = True
            save_phones(phones)
            print_success(f"active: {p['name']} → portmap public {p['public_port']} / local {p['local_port']}")
            print("  [dim]now run 64 (Full Access) or 67 (Re-Access) for this phone[/dim]")
        elif choice == "d":
            idx = _select_index(phones, "delete which phone")
            if idx is None:
                continue
            removed = phones.pop(idx)
            save_phones(phones)
            print_warning(f"removed {removed['name']}")


def _console():
    from modules.console import console

    return console