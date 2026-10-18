#!/usr/bin/env python3
"""Quick command sender for Andro-DLS C2 server."""
import sys, os

CMD_FILE = "/tmp/c2_pending_cmd"
cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "NONE"

with open(CMD_FILE, "w") as f:
    f.write(cmd)

print(f"[*] Command queued: {cmd}")
print(f"[*] Agent will pick it up on next beacon (within 60s)")