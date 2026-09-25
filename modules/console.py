import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.theme import Theme

from modules.config import AppConfig

# ctOS-inspired black/white theme — Watch Dogs aesthetic
_theme = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "prompt": "bold white",
        "highlight": "bold white",
        "muted": "dim white",
        "border": "white",
        "data": "white",
        "label": "dim white",
        "accent": "cyan",
    }
)

console = Console(theme=_theme, highlight=False)

STATUS_SPINNER = "dots"


def task_status(message: str):
    """Transient operation line — Rich updates in place until the block exits."""
    return console.status(message, spinner=STATUS_SPINNER)


def submenu_row(*labels: str) -> None:
    """Compact one-line submenu: 1) …  2) …"""
    parts = [f"[dim]{i}[/dim] {text}" for i, text in enumerate(labels, 1)]
    console.print("  " + "   ".join(parts))


_ConfigDirAttr = Literal["pull_location", "screenshot_location", "screenrecord_location"]


_device_subfolder_cache: str | None = None


def device_subfolder() -> str:
    """Sanitized device model name used as the top-level download folder
    (e.g. 'Infinix_X6880'). Falls back to 'Unknown-Device' when no device
    is attached. Cached for the process lifetime."""
    global _device_subfolder_cache
    if _device_subfolder_cache is not None:
        return _device_subfolder_cache
    name = ""
    exe = get_adb_executable()
    if exe:
        try:
            serial = os.environ.get("ANDROID_SERIAL", "")
            if not serial:
                r = subprocess.run([exe, "devices"], capture_output=True, text=True)
                for line in r.stdout.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        serial = parts[0]
                        break
            if serial:
                r = subprocess.run(
                    [exe, "-s", serial, "shell", "getprop", "ro.product.marketname"],
                    capture_output=True,
                    text=True,
                )
                name = r.stdout.strip()
                if not name or "unknown" in name.lower():
                    r = subprocess.run(
                        [exe, "-s", serial, "shell", "getprop", "ro.product.model"],
                        capture_output=True,
                        text=True,
                    )
                    name = r.stdout.strip()
        except Exception:
            name = ""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") if name else ""
    _device_subfolder_cache = name or "Unknown-Device"
    return _device_subfolder_cache


def ensure_config_dir(
    config: AppConfig,
    field: _ConfigDirAttr,
    category: str | None = None,
    default: str = "Downloaded-Files",
) -> Path:
    """Resolve a download destination."""
    val = getattr(config, field)
    if not val:
        val = (
            ask(
                f"[yellow]Output folder[/yellow] [dim](Enter={default})[/dim]> "
            ).strip()
            or default
        )
        setattr(config, field, val)
    p = Path(val) / device_subfolder()
    if category:
        p = p / category
    p.mkdir(parents=True, exist_ok=True)
    return p


def print_error(msg: str) -> None:
    console.print(f"[error]\\[Error][/error] [white]{msg}[/white]")


def print_success(msg: str) -> None:
    console.print(f"[success]{msg}[/success]")


def print_warning(msg: str) -> None:
    console.print(f"[warning]\\[Warning][/warning] [white]{msg}[/white]")


def print_info(msg: str) -> None:
    console.print(f"[info]{msg}[/info]")


def print_null_input() -> None:
    console.print("[error]Null input[/error]. [green]Returning to menu.[/green]")


def ask(prompt: str) -> str:
    """Styled input prompt that survives terminal line editing."""
    rendered = _render_prompt(prompt)
    if _readline_is_gnu():
        rendered = _wrap_ansi_escapes(rendered)
    try:
        return input(rendered)
    except EOFError:
        return ""


def _render_prompt(prompt: str) -> str:
    """Render rich-markup prompt to the ANSI string shown by input()."""
    with console.capture() as capture:
        console.print(prompt, end="")
    return capture.get()


_readline_backend_checked = False
_readline_backend_gnu = False


def _readline_is_gnu() -> bool:
    """True when the active readline is GNU readline (not libedit/None)."""
    global _readline_backend_checked, _readline_backend_gnu
    if not _readline_backend_checked:
        try:
            import readline
        except ImportError:
            _readline_backend_gnu = False
        else:
            _readline_backend_gnu = "GNU" in (getattr(readline, "__doc__", "") or "")
        _readline_backend_checked = True
    return _readline_backend_gnu


_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _wrap_ansi_escapes(text: str) -> str:
    """Wrap ANSI escapes in \\x01..\\x02 so GNU readline ignores their width."""
    return _ANSI_ESCAPE.sub(lambda m: f"\x01{m.group(0)}\x02", text)


def confirm(prompt: str = "Do you want to continue?") -> bool:
    """Ask Y/N confirmation. Returns True for yes/enter, False for no."""
    choice = ask(f"\n[white]{prompt}     [bold]Y / N[/bold][/white] > ").lower()
    while choice not in ("y", "n", ""):
        choice = ask("[error]Invalid choice![/error] Press Y or N > ").lower()
    return choice in ("y", "")


def open_file_prompt(opener: str, path: str) -> None:
    """Ask user if they want to open the resulting file."""
    if confirm("Do you want to open the file?"):
        subprocess.run([opener, path], check=False)


_adb_executable: str | None = None


def set_adb_executable(path: str | None) -> None:
    """Set after tools.resolve_external_tools; None means ADB was not found."""
    global _adb_executable
    _adb_executable = path


def get_adb_executable() -> str | None:
    """Resolved adb path from startup, or None if not available."""
    return _adb_executable


def adb(args: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    """Run an adb command."""
    if _adb_executable is None:
        return subprocess.CompletedProcess(
            args=[],
            returncode=127,
            stdout="",
            stderr="adb not available",
        )
    cmd = [_adb_executable] + args
    if capture:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    return subprocess.run(cmd)


def adb_output(args: list[str]) -> str:
    """Run an adb command and return stripped stdout."""
    return adb(args).stdout.strip()
