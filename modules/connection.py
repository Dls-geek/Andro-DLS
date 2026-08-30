import ipaddress
import os
import re
import socket
import subprocess
import time
import nmap
from rich.table import Table

from modules.config import AppConfig
from modules.console import (
    console,
    print_error,
    print_success,
    print_null_input,
    confirm,
    task_status,
    adb,
    adb_output,
    get_adb_executable,
    ask,
)


def get_ip_address() -> str | None:
    """Best-effort LAN IP for LHOST / scanning. Returns None if offline or unreachable."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3.0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def _sort_ipv4(hosts: list[str]) -> list[str]:
    return sorted(hosts, key=lambda h: int(ipaddress.IPv4Address(h)))


def _adb_port_summary(host_data: dict) -> str:
    """Describe open 5555/5554 and any -sV fingerprint (e.g. Android Debug Bridge)."""
    tcp = host_data.get("tcp") or {}
    lines: list[str] = []
    for port in (5555, 5554):
        pinfo = tcp.get(port)
        if not pinfo or pinfo.get("state") != "open":
            continue
        product = (pinfo.get("product") or "").strip()
        version = (pinfo.get("version") or "").strip()
        extra = (pinfo.get("extrainfo") or "").strip()
        name = (pinfo.get("name") or "").strip()
        bits: list[str] = [f"{port}/tcp open"]
        if product:
            bits.append(product)
        elif name and name != "unknown":
            bits.append(name)
        if version:
            bits.append(version)
        if extra and extra not in product:
            bits.append(extra)
        lines.append(" ".join(bits))
    return " · ".join(lines) if lines else ""


def _android_hint(adb_summary: str) -> str:
    """Interpret ADB port probe only (no MAC/hostname/OUI)."""
    if not adb_summary:
        return ""
    a = adb_summary.lower()
    if "android debug bridge" in a or "free adb" in a:
        return "Strong: ADB fingerprint"
    if "5555/tcp open" in adb_summary or "5554/tcp open" in adb_summary:
        return "Strong: ADB port open (wireless/emulator)"
    if "adb" in a and "open" in a:
        return "Likely: ADB-related port"
    return ""


def is_valid_ipv4(address: str) -> bool:
    parts = address.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _list_ready_device_serials() -> list[str]:
    """Serial numbers of devices in the `device` state (authorized, ready)."""
    exe = get_adb_executable()
    if not exe:
        return []
    result = subprocess.run([exe, "devices"], capture_output=True, text=True)
    serials: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        serial, _, rest = line.partition("\t")
        serial = serial.strip()
        state = rest.split()[0] if rest.split() else ""
        if state == "device":
            serials.append(serial)
    return serials


def prompt_select_device_if_multiple(config: AppConfig) -> None:
    """
    Set ANDROID_SERIAL for this process when multiple USB/network devices are connected.
    adb honors ANDROID_SERIAL as the default target (see Android platform-tools docs).
    """
    if not config.adb_path:
        os.environ.pop("ANDROID_SERIAL", None)
        return

    serials = _list_ready_device_serials()
    if not serials:
        os.environ.pop("ANDROID_SERIAL", None)
        return
    if len(serials) == 1:
        os.environ["ANDROID_SERIAL"] = serials[0]
        return

    table = Table(
        title="Multiple devices detected",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="bold green", justify="right")
    table.add_column("Serial", style="white")
    for i, s in enumerate(serials, 1):
        table.add_row(str(i), s)

    console.print(table)
    console.print("[yellow]Choose default device for this session.[/yellow]")
    choice = ask(
        f"[prompt]Enter 1–{len(serials)} (Enter = first) > [/prompt]"
    ).strip()
    idx = 0
    if choice.isdigit():
        n = int(choice)
        if 1 <= n <= len(serials):
            idx = n - 1
    os.environ["ANDROID_SERIAL"] = serials[idx]
    console.print(f"[green]Using device[/green] [white]{serials[idx]}[/white]")


def connect(config: AppConfig) -> None:
    console.print(
        "[cyan]Target phone IP[/cyan] [dim](e.g. 192.168.1.23)[/dim]"
    )
    ip = ask("[prompt]> [/prompt]").strip()
    if not ip:
        print_null_input()
        return

    if not is_valid_ipv4(ip):
        print_error("Invalid IPv4 address\n[green] Going back to Main Menu[/green]")
        return

    if not confirm(
        "Connecting will [yellow]restart the ADB server[/yellow] and may disconnect "
        "other active ADB sessions on this computer. Continue?"
    ):
        return

    adb_exe = get_adb_executable()
    if not adb_exe:
        print_error("ADB executable not available.")
        return

    with task_status("[info]Restarting ADB server…[/info]"):
        subprocess.run(
            [adb_exe, "kill-server"],
            capture_output=True,
        )
        subprocess.run(
            [adb_exe, "start-server"],
            capture_output=True,
        )

    with task_status(f"[info]Connecting to {ip}:5555…[/info]"):
        result = adb(["connect", f"{ip}:5555"])

    output = result.stdout.strip()
    if "connected" in output.lower():
        print_success(output)
        prompt_select_device_if_multiple(config)
    else:
        print_error(output or result.stderr.strip())


def list_devices(config: AppConfig) -> None:
    with task_status("[info]Fetching connected devices…[/info]"):
        result = adb(["devices", "-l"])

    lines = result.stdout.strip().splitlines()
    if len(lines) <= 1:
        console.print("[yellow]No devices connected.[/yellow]")
        return

    table = Table(title="Connected Devices", show_header=True, header_style="bold cyan")
    table.add_column("Device", style="white")
    table.add_column("State", style="green")
    table.add_column("Info", style="dim white")

    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split()
        device = parts[0] if len(parts) > 0 else ""
        state = parts[1] if len(parts) > 1 else ""
        info = " ".join(parts[2:]) if len(parts) > 2 else ""
        table.add_row(device, state, info)

    console.print(table)


def disconnect(config: AppConfig) -> None:
    if not confirm("Disconnect [bold]all[/bold] ADB devices?"):
        return
    with task_status("[info]Disconnecting…[/info]"):
        result = adb(["disconnect"])
    os.environ.pop("ANDROID_SERIAL", None)
    console.print(f"[green]{result.stdout.strip()}[/green]")


def stop_adb(config: AppConfig) -> None:
    if not confirm(
        "Stop the ADB server? [yellow]All device connections will be lost[/yellow] until you start ADB again."
    ):
        return
    with task_status("[info]Stopping ADB server…[/info]"):
        adb(["kill-server"])
    os.environ.pop("ANDROID_SERIAL", None)
    print_success("ADB server stopped.")


def _port_scanner(config: AppConfig) -> nmap.PortScanner:
    """Use the same nmap binary as startup resolution when available."""
    if config.nmap_path:
        return nmap.PortScanner(nmap_search_path=(config.nmap_path,))
    return nmap.PortScanner()


def scan_network(config: AppConfig) -> None:
    ip = get_ip_address()
    if ip is None:
        print_error(
            "Could not detect a local IP address. Check your network connection and try again."
        )
        return
    subnet = ip + "/24"

    discover = _port_scanner(config)
    with task_status(f"[info]Discovering hosts on {subnet}…[/info]"):
        discover.scan(hosts=subnet, arguments="-sn")

    hosts = [
        h
        for h in discover.all_hosts()
        if discover[h]["status"]["state"] == "up"
    ]
    hosts = _sort_ipv4(hosts)

    if not hosts:
        console.print("[yellow]No hosts found.[/yellow]")
        return

    ports_scan = _port_scanner(config)
    with task_status(
        "[info]Probing ADB ports 5555/5554 (TCP + service probe) on live hosts…[/info]"
    ):
        try:
            ports_scan.scan(
                hosts=" ".join(hosts),
                arguments="-p 5555,5554 -sT -sV --version-intensity 1 -T4",
            )
        except nmap.PortScannerError as e:
            print_error(f"ADB port scan failed: {e}")
            ports_scan = None

    table = Table(title=f"Network Scan — {subnet}", show_header=True, header_style="bold cyan")
    table.add_column("IP Address", style="bold green")
    table.add_column("ADB 5555 / 5554", style="cyan")
    table.add_column("Android?", style="yellow")

    for host in hosts:
        adb_summary = ""
        if ports_scan and host in ports_scan.all_hosts():
            adb_summary = _adb_port_summary(ports_scan[host])
        hint = _android_hint(adb_summary)
        table.add_row(
            host,
            adb_summary or "—",
            hint or "—",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# AUTO CONNECT — one-key connect: USB first (tcpip 5555 + Wi-Fi IP), else LAN scan
# ---------------------------------------------------------------------------

def _usb_ready_serials() -> list[str]:
    """USB-attached, authorized devices (serial without :port)."""
    exe = get_adb_executable()
    if not exe:
        return []
    result = subprocess.run([exe, "devices"], capture_output=True, text=True)
    serials: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        serial, _, rest = line.partition("\t")
        serial = serial.strip()
        state = rest.split()[0] if rest.split() else ""
        if state == "device" and ":" not in serial:
            serials.append(serial)
    return serials


def _device_wifi_ip(serial: str) -> str | None:
    """Best-effort Wi-Fi IP of a USB-connected device."""
    candidates = (
        ["shell", "ip", "-f", "inet", "addr", "show", "wlan0"],
        ["shell", "ifconfig", "wlan0"],
        ["shell", "ip", "addr", "show", "wlan0"],
        ["shell", "ip", "route", "get", "8.8.8.8"],
    )
    for args in candidates:
        out = adb(["-s", serial, *args]).stdout
        if not out:
            continue
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out) or re.search(
            r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", out
        )
        if m:
            ip = m.group(1)
            if ip != "127.0.0.1" and not ip.startswith("169.254."):
                return ip
    return None


def _connect_and_verify(ip: str) -> bool:
    """adb connect ip:5555 and confirm the target is in `device` state."""
    with task_status(f"[info]Connecting to {ip}:5555…[/info]"):
        result = adb(["connect", f"{ip}:5555"])
    if "connected" not in result.stdout.strip().lower():
        return False
    return f"{ip}:5555" in _list_ready_device_serials()


def _scan_for_adb_hosts(config: AppConfig, subnet: str) -> list[str]:
    """Live hosts on the subnet with TCP 5555 open (light probe)."""
    scanner = _port_scanner(config)
    try:
        with task_status(f"[info]Scanning {subnet} for devices…[/info]"):
            scanner.scan(hosts=subnet, arguments="-sn")
        live = [h for h in scanner.all_hosts() if scanner[h]["status"]["state"] == "up"]
        if not live:
            return []
        with task_status("[info]Probing ADB port 5555…[/info]"):
            scanner.scan(hosts=" ".join(live), arguments="-p 5555 -sT --open -T4")
        hits = [
            h
            for h in live
            if h in scanner.all_hosts()
            and scanner[h].get("tcp", {}).get(5555, {}).get("state") == "open"
        ]
        return _sort_ipv4(hits)
    except nmap.PortScannerError as e:
        print_error(f"Network scan failed: {e}")
        return []


def auto_connect(config: AppConfig) -> None:
    """One-key auto connect:
    1) USB device attached → tcpip 5555 → read its Wi-Fi IP → connect.
    2) No USB → scan LAN for open ADB port 5555 and connect to the first hit.
    No manual IP entry needed.
    """
    adb_exe = get_adb_executable()
    if not adb_exe:
        print_error("ADB executable not available.")
        return

    console.print("\n[bold cyan][ AUTO CONNECT ][/bold cyan] Checking USB devices…")
    with task_status("[info]Restarting ADB server…[/info]"):
        subprocess.run([adb_exe, "kill-server"], capture_output=True)
        subprocess.run([adb_exe, "start-server"], capture_output=True)

    all_lines = adb(["devices"]).stdout.splitlines()[1:]
    if any("unauthorized" in line for line in all_lines):
        print_error(
            "Phone is attached but [bold]unauthorized[/bold] — accept the "
            "'Allow USB debugging?' popup on the phone, then press 1 again."
        )
        return

    usb_serials = _usb_ready_serials()
    if usb_serials:
        serial = usb_serials[0]
        console.print(f"[green]USB device found:[/green] [white]{serial}[/white]")
        with task_status("[info]Enabling ADB over Wi-Fi (tcpip 5555)…[/info]"):
            adb(["-s", serial, "tcpip", "5555"])
        time.sleep(2)
        ip = _device_wifi_ip(serial)
        if ip:
            console.print(f"[green]Device Wi-Fi IP:[/green] [white]{ip}[/white]")
            if _connect_and_verify(ip):
                os.environ["ANDROID_SERIAL"] = f"{ip}:5555"
                print_success(f"Auto-connected to {ip}:5555 over Wi-Fi ✓")
                return
            print_error(f"Connection to {ip}:5555 failed.")
        else:
            print_error("Could not read the device Wi-Fi IP — falling back to LAN scan.")
    else:
        console.print("[yellow]No USB device attached — scanning LAN for ADB devices…[/yellow]")

    local_ip = get_ip_address()
    if local_ip is None:
        print_error("Cannot detect the local network. Connect a USB cable or check Wi-Fi.")
        return

    subnet = local_ip + "/24"
    hits = _scan_for_adb_hosts(config, subnet)
    if not hits:
        print_error(f"No device with open ADB port 5555 found on {subnet}.")
        console.print(
            "[yellow]Connect the phone via USB once (option 1) to enable "
            "ADB over Wi-Fi, or plug it in and retry.[/yellow]"
        )
        return

    for host in hits:
        if _connect_and_verify(host):
            os.environ["ANDROID_SERIAL"] = f"{host}:5555"
            print_success(f"Auto-connected to {host}:5555 ✓")
            return

    print_error("Found ADB ports, but connections failed (offline/unauthorized).")
