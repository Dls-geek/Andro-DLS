import os
import platform
import random
import shutil
import subprocess
from pathlib import Path

from rich.panel import Panel

from modules import banner, color
from modules.config import AppConfig
from modules.console import console, confirm, print_error, set_adb_executable, ask
from modules.tools import (
    resolve_external_tools,
    require_adb,
    require_metasploit,
    require_nmap,
    require_scrcpy,
)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _detect_platform(config: AppConfig) -> None:
    config.operating_system = platform.system()
    if config.operating_system == "Windows":
        config.clear_cmd = "cls"
        config.opener = "start"
    elif config.operating_system == "Darwin":
        config.opener = "open"
    # Linux default: clear_cmd="clear", opener="xdg-open"

    if config.operating_system != "Windows":
        import readline  # noqa: F401  — enables arrow keys in input


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _collect_missing_tools(config: AppConfig) -> list[tuple[str, str]]:
    """Return list of (display name, installer component key)."""
    missing: list[tuple[str, str]] = []
    if not config.adb_path:
        missing.append(("ADB", "adb"))
    if not config.msfvenom_path or not config.msfconsole_path:
        missing.append(("Metasploit-Framework (msfvenom & msfconsole)", "metasploit"))
    if not config.scrcpy_path:
        missing.append(("Scrcpy", "scrcpy"))
    if not config.nmap_path:
        missing.append(("Nmap", "nmap"))
    return missing


def _run_dependency_installer(config: AppConfig, component_keys: list[str]) -> None:
    """Run install.sh (Unix) or install.ps1 (Windows) for the given component keys."""
    root = _project_root()
    keys = list(dict.fromkeys(component_keys + ["pip"]))
    joined = ",".join(keys)

    if config.operating_system == "Windows":
        ps = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
        script = root / "install.ps1"
        if not script.is_file():
            print_error(f"Installer not found: {script}")
            return
        if not ps:
            print_error("PowerShell not found on PATH. Install dependencies manually (see README).")
            return
        subprocess.run(
            [
                ps,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Components",
                joined,
                "-NonInteractive",
            ],
            cwd=str(root),
        )
    else:
        script = root / "install.sh"
        if not script.is_file():
            print_error(f"Installer not found: {script}")
            return
        subprocess.run(
            ["bash", str(script), "--yes", "--components", joined],
            cwd=str(root),
        )

    console.print(
        "[dim]If tools are still not detected, open a new terminal and run PhoneSploit Pro again "
        "(PATH may need a refresh).[/dim]"
    )


def check_packages(config: AppConfig) -> None:
    while True:
        missing = _collect_missing_tools(config)
        if not missing:
            return

        names = [name for name, _ in missing]
        items = "\n".join(
            f"  [bold yellow]{i + 1}.[/bold yellow] [white]{name}[/white]"
            for i, name in enumerate(names)
        )
        console.print(
            Panel(
                f"[red]The following required tools are NOT installed:[/red]\n\n{items}\n\n"
                "[cyan]Install them manually (see README) or use the automatic installer.[/cyan]",
                title="[bold red]Missing Dependencies[/bold red]",
                border_style="red",
            )
        )

        prompt = (
            "\n[yellow]Press [bold]I[/bold] to install missing tools automatically · "
            "[bold]Y[/bold] continue anyway · [bold]N[/bold] exit[/yellow] > "
        )
        choice = ask(prompt).strip().lower()

        while choice not in ("i", "y", "n", "", "yes", "no"):
            choice = ask("[red]Invalid choice![/red] Press I, Y, or N > ").strip().lower()

        if choice in ("n", "no"):
            raise SystemExit(0)
        if choice in ("i",):
            keys = [k for _, k in missing]
            _run_dependency_installer(config, keys)
            resolve_external_tools(config)
            set_adb_executable(config.adb_path)
            continue
        if choice in ("y", "", "yes"):
            return


def start(config: AppConfig) -> None:
    Path("Downloaded-Files").mkdir(exist_ok=True)
    _detect_platform(config)
    resolve_external_tools(config)
    set_adb_executable(config.adb_path)
    check_packages(config)


# ---------------------------------------------------------------------------
# Menu display
# ---------------------------------------------------------------------------

_selected_banner: str = ""


def _pick_banner() -> str:
    c = random.choice(color.color_list)
    return f"[bold {c}]{random.choice(banner.banner_list)}[/bold {c}]"


def display_menu(config: AppConfig) -> None:
    global _selected_banner
    console.print(_selected_banner)
    console.print(banner.menu[config.page_number])


def clear_screen(config: AppConfig) -> None:
    os.system(config.clear_cmd)
    display_menu(config)


def change_page(config: AppConfig, direction: str) -> None:
    if direction == "p" and config.page_number > 0:
        config.page_number -= 1
    elif direction == "n" and config.page_number < 4:
        config.page_number += 1
    clear_screen(config)


# ---------------------------------------------------------------------------
# Misc actions
# ---------------------------------------------------------------------------

def update_me(config: AppConfig) -> None:
    if not confirm(
        "Run [cyan]git fetch[/cyan] and [cyan]git rebase[/cyan] to update PhoneSploit-Pro? "
        "Uncommitted local changes may conflict or be lost."
    ):
        return
    console.print("[yellow]Updating PhoneSploit-Pro...[/yellow]")
    console.print("[green]Fetching latest updates from GitHub...[/green]")
    fetch = subprocess.run(
        ["git", "fetch"],
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        detail = (fetch.stdout + fetch.stderr).strip() or f"exit code {fetch.returncode}"
        print_error(f"git fetch failed: {detail}")
        return

    console.print("[green]Applying changes...[/green]")
    rebase = subprocess.run(
        ["git", "rebase"],
        capture_output=True,
        text=True,
    )
    if rebase.returncode != 0:
        detail = (rebase.stdout + rebase.stderr).strip() or f"exit code {rebase.returncode}"
        print_error(f"git rebase failed: {detail}")
        console.print(
            "[yellow]If rebase stopped with conflicts, fix the files, then run "
            "[cyan]git rebase --continue[/cyan]. To give up and restore the previous state, run "
            "[cyan]git rebase --abort[/cyan].[/yellow]"
        )
        return

    console.print("[cyan]Please restart PhoneSploit-Pro.[/cyan]")
    config.run = False


# ---------------------------------------------------------------------------
# Main dispatch loop
# ---------------------------------------------------------------------------

def main(config: AppConfig) -> None:
    from modules import autoflow

    option = ask("[red]\\[Main Menu][/red] > ").strip().lower()

    match option:
        case "p" | "n" | "99":
            console.print("[dim](legacy pages removed — this build is focused)[/dim]")
        case "0":
            config.run = False
            console.print("\n[white]Exiting...[/white]\n")
        case "1":
            try:
                autoflow.auto_connect(config)
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]cancelled[/yellow]")
            except Exception as e:
                console.print(f"[red]Auto Connect error:[/red] {e}")
        case "2":
            try:
                from modules import devices as devstore

                devs = devstore.load_store()
                if not devs:
                    console.print("[yellow]no saved devices — run 1 (AUTO CONNECT) first[/yellow]")
                    return
                if len(devs) == 1:
                    d = devs[0]
                else:
                    for i, x in enumerate(devs, 1):
                        console.print(f"  [white]{i}.[/white] {x.get('name') or x.get('serial')}")
                    c = ask("[cyan]which phone[/cyan]> ").strip()
                    if not (c.isdigit() and 1 <= int(c) <= len(devs)):
                        console.print("[red]invalid[/red]")
                        return
                    d = devs[int(c) - 1]

                from modules.pentest import pentest_menu

                pentest_menu(config, d)
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]cancelled[/yellow]")
            except Exception as e:
                console.print(f"[red]Reconnect error:[/red] {e}")
        case "3":
            try:
                autoflow.portmap_setup(config)
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]cancelled[/yellow]")
            except Exception as e:
                console.print(f"[red]Portmap error:[/red] {e}")
        case _:
            console.print("\n[red]Invalid selection![/red]\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    global _selected_banner
    config = AppConfig()
    start(config)

    _selected_banner = _pick_banner()
    clear_screen(config)

    while config.run:
        try:
            main(config)
        except KeyboardInterrupt:
            config.run = False
            console.print("\n[white]Exiting...[/white]\n")
        except Exception as e:  # never let one bad option kill the CLI
            console.print(f"\n[red]Unexpected error:[/red] {e}\n[yellow]Back to main menu.[/yellow]\n")
