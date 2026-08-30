"""Permanent reverse-tunnel management for remote device access.

Providers (auto-pick by availability/config):
  pinggy    — free, NO account, but endpoint expires (~60 min). Auto-restart + re-resolve.
  ngrok     — free w/ authtoken (NGROK_AUTHTOKEN env or ~/.config/ngrok/ngrok.yml).
              Free endpoint rotates; loop keeps it alive & rebuilds payload on change.
  portmap   — free ACCOUNT, STABLE endpoint forever. Env: PM_USER, PM_HOST, PM_PORT,
              PM_SSH_PORT (default 2222). This is the "permanent" choice.
  cloudflared — if CLOUDFLARED_CMD set (named tunnel w/ domain = permanent).

On endpoint change, callback(endpoint) lets the caller rebuild/reinstall the payload.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent / ".payload-build" / "portmap.json"


def load_portmap_config() -> dict | None:
    """Load saved portmap.io account."""
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return None
    return None


def save_portmap_config(
    host: str, user: str, ssh_port: str, public_port: str, key: str = "",
    ssh_host: str = "portmap.io", dial_host: str = "",
) -> dict:
    cfg = {
        "host": host.strip(),
        "ssh_host": ssh_host.strip() or "portmap.io",
        "user": user.strip(),
        "ssh_port": ssh_port.strip() or "2222",
        "public_port": public_port.strip(),
        "key": key.strip(),
        "dial_host": dial_host.strip() or host.strip(),
    }
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    return cfg


def portmap_setup_interactive() -> dict | None:
    """Guide the operator through entering their portmap.io details once."""
    from modules.console import ask, print_error, print_success

    print("\n[bold cyan]▸ PORTMAP.IO SETUP[/bold cyan]  (permanent tunnel — enter once, reuse always)")
    print("[dim]Instruction box: 'ssh -i key user@host -f -N -R XXXX:localhost:YY' — copy from it[/dim]\n")
    user = ask("[cyan]Username[/cyan] [dim](e.g. v-xxxx.config)[/dim]> ").strip()
    key = ask("[cyan]Full path to .pem key[/cyan] [dim](e.g. /home/you/.ssh/v-xxx.pem)[/dim]> ").strip()
    pub_port = ask("[cyan]Public port (XXXX)[/cyan] [dim](portmap e 'Port on Portmap.io' field)[/dim]> ").strip()
    local_port = ask("[cyan]Local port (YY on your PC)[/cyan] [dim](e.g. 4445)[/dim]> ").strip() or "4445"
    dial_host = ask(
        "[cyan]Dial host (phone will connect here)[/cyan] "
        "[dim](e.g. yourmap-xxxx.portmap.host or portmap.io)[/dim]> "
    ).strip()
    if not user or not pub_port:
        print_error("username + public port required — nothing saved")
        return None
    cfg = save_portmap_config(dial_host, user, "2222", pub_port, key, "portmap.io", dial_host)
    print_success(
        f"portmap saved: {user}@portmap.io -R {pub_port}:localhost:{local_port}\n"
        f"  phone dials: {cfg['dial_host']}:{pub_port}"
    )
    # stash local port too so payload/listener use it
    try:
        env_path = Path(__file__).resolve().parent.parent / ".payload-build" / "portmap.json"
        cfg["local_port"] = local_port
        env_path.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass
    return cfg


@dataclass
class Tunnel:
    provider: str
    endpoint_host: str = ""
    endpoint_port: str = ""
    proc: subprocess.Popen | None = None
    log_path: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def endpoint(self) -> str:
        return f"{self.endpoint_host}:{self.endpoint_port}" if self.endpoint_host else ""


def _pick_provider() -> str:
    if os.environ.get("PORTMAP_HOST") and os.environ.get("PORTMAP_USER"):
        return "portmap"
    if os.environ.get("CLOUDFLARED_CMD"):
        return "cloudflared"
    if os.environ.get("NGROK_AUTHTOKEN") or os.path.exists(
        os.path.expanduser("~/.config/ngrok/ngrok.yml")
    ):
        return "ngrok"
    return "pinggy"


def _start_ssh_tunnel(cmd: list[str], log_path: str) -> subprocess.Popen:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "wb") as f:
        return subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)


def _parse_pinggy(log_path: str) -> tuple[str, str] | None:
    try:
        with open(log_path, "r", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r"tcp://([^\s]+):(\d+)", text)
    return (m.group(1), m.group(2)) if m else None


def _parse_ngrok(log_path: str) -> tuple[str, str] | None:
    try:
        with open(log_path, "r", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r"tcp://([^\s]+):(\d+)", text)
    return (m.group(1), m.group(2)) if m else None


def start_tunnel(lport: int, provider: str | None = None) -> Tunnel:
    provider = provider or _pick_provider()
    log_dir = "pipeline/logs"
    os.makedirs(log_dir, exist_ok=True)
    t = Tunnel(provider=provider, log_path=f"{log_dir}/tunnel-{provider}.log")

    if provider == "portmap":
        cfg = load_portmap_config()
        if cfg:
            ssh_host = cfg.get("ssh_host", "portmap.io")
            user = cfg.get("user", "")
            ssh_port = cfg.get("ssh_port", "2222")
            pub_port = cfg.get("public_port", str(lport))
            key = cfg.get("key", "")
            dial_host = cfg.get("dial_host", cfg.get("host", ssh_host))
            local_port = int(cfg.get("local_port", lport))
        else:
            ssh_host = os.environ.get("PORTMAP_SSH_HOST", "portmap.io")
            user = os.environ.get("PORTMAP_USER", "")
            ssh_port = os.environ.get("PORTMAP_SSH_PORT", "2222")
            pub_port = os.environ.get("PORTMAP_PUBLIC_PORT", str(lport))
            key = os.environ.get("PORTMAP_KEY", "")
            dial_host = os.environ.get("PORTMAP_HOST", ssh_host)
            local_port = lport
        if not user or not key:
            t.endpoint_host = ""
            return t

        # Use paramiko (pure-python SSH) — the system `ssh` binary sometimes
        # fails to parse portmap keys (OpenSSL3 libcrypto quirk), while
        # paramiko loads them fine.
        try:
            import paramiko
        except ImportError:
            print("[!] paramiko not installed — pip install paramiko", flush=True)
            t.endpoint_host = ""
            return t
        try:
            pkey = paramiko.RSAKey.from_private_key_file(key)
        except Exception:
            try:
                pkey = paramiko.Ed25519Key.from_private_key_file(key)
            except Exception as e:
                print(f"[!] cannot load key {key}: {e}", flush=True)
                t.endpoint_host = ""
                return t
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connected = False
        last_err = None
        for attempt in range(3):
            try:
                cli.connect(
                    ssh_host, port=int(ssh_port), username=user, pkey=pkey,
                    timeout=15, allow_agent=False, look_for_keys=False,
                    banner_timeout=60, auth_timeout=45,
                )
                connected = True
                break
            except Exception as e:
                last_err = e
                time.sleep(3)
        if not connected:
            print(f"[!] portmap ssh connect failed (3 tries): {last_err}", flush=True)
            t.endpoint_host = ""
            return t
        ch = cli.get_transport().request_port_forward("", int(pub_port))
        if not ch:
            print(f"[!] remote port forward {pub_port} denied", flush=True)
            cli.close()
            t.endpoint_host = ""
            return t
        t.proc = cli  # reuse field: keep client alive
        t.endpoint_host, t.endpoint_port = dial_host, pub_port
        print(f"[tunnel] portmap live: {dial_host}:{pub_port} -> localhost:{local_port}", flush=True)
        # ---- forwarding loop: forwarded-tcpip channels -> local listener
        def _pump(cli_conn, lport_):
            import socket as _s

            while True:
                try:
                    chan = cli_conn.get_transport().accept(1)
                except Exception:
                    return
                if chan is None:
                    continue
                # log the forwarded-conn originator when portmap provides it
                try:
                    oip = chan.get_originator_ipv4()
                    oport = chan.get_originator_port()
                    print(f"[pump] incoming forwarded conn from {oip}:{oport}", flush=True)
                except Exception:
                    print("[pump] incoming forwarded conn (originator n/a)", flush=True)
                try:
                    local = _s.create_connection(("127.0.0.1", lport_), timeout=5)
                except Exception:
                    chan.close()
                    continue
                chan.settimeout(None)
                local.settimeout(None)

                def pipe(a, b):
                    try:
                        while True:
                            d = a.recv(65536)
                            if not d:
                                break
                            b.sendall(d)
                    except Exception:
                        pass
                    finally:
                        for s_ in (a, b):
                            try:
                                s_.close()
                            except Exception:
                                pass

                import threading as _th

                _th.Thread(target=pipe, args=(chan, local), daemon=True).start()
                _th.Thread(target=pipe, args=(local, chan), daemon=True).start()

        threading.Thread(target=_pump, args=(cli, local_port), daemon=True).start()
        return t

    if provider == "cloudflared":
        cmd = os.environ["CLOUDFLARED_CMD"].replace("{lport}", str(lport)).split()
        t.proc = _start_ssh_tunnel(cmd, t.log_path)
        # endpoint parsed manually later; fixed host usually
        return t

    if provider == "ngrok":
        cmd = ["ngrok", "tcp", str(lport), "--log=stdout"]
        t.proc = _start_ssh_tunnel(cmd, t.log_path)
    else:  # pinggy
        cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
            "-o", "ExitOnForwardFailure=yes", "-p", "443",
            "-R", f"0:localhost:{lport}", "tcp@a.pinggy.io",
        ]
        t.proc = _start_ssh_tunnel(cmd, t.log_path)

    # wait for endpoint (pinggy up to ~15 s; ngrok ~5 s)
    parser = _parse_pinggy if provider == "pinggy" else _parse_ngrok
    deadline = time.time() + 25
    while time.time() < deadline:
        if t.proc.poll() is not None:
            break
        ep = parser(t.log_path)
        if ep:
            t.endpoint_host, t.endpoint_port = ep
            break
        time.sleep(1)
    return t


def wait_loop(t: Tunnel, lport: int, on_change, stop_event: threading.Event) -> None:
    """Keep the tunnel alive; call on_change(new_endpoint, why) whenever the
    public endpoint changes or on (re)start. Blocks until stop_event set."""
    prev = ""
    while not stop_event.is_set():
        if t.proc is None or t.proc.poll() is not None:
            t.proc = restart_tunnel(t, lport)
        ep = f"{t.endpoint_host}:{t.endpoint_port}" if t.endpoint_host else ""
        parser = _parse_pinggy if t.provider == "pinggy" else _parse_ngrok
        if t.provider in ("pinggy", "ngrok"):
            got = parser(t.log_path)
            if got:
                host, port = got
                ep = f"{host}:{port}"
                if (host, port) != (t.endpoint_host, t.endpoint_port):
                    t.endpoint_host, t.endpoint_port = host, port
        if ep and ep != prev:
            prev = ep
            on_change(ep)
        time.sleep(10)


def restart_tunnel(t: Tunnel, lport: int) -> subprocess.Popen:
    t.proc.kill() if t.proc else None
    # same provider restart
    return start_tunnel(lport, t.provider).proc


def stop_tunnel(t: Tunnel) -> None:
    if t.proc:
        try:
            # paramiko client or subprocess
            if hasattr(t.proc, "close"):
                t.proc.close()
            else:
                t.proc.terminate()
        except Exception:
            pass