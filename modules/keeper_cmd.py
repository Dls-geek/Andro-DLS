"""One-shot command through the keeper's device session (non-interactive).

Send ONE shell command to the live phone and capture its reply, without
entering interactive mode. Used by CLI control options when the phone is
off-LAN (internet path).
"""
import socket
import sys
import time

CTRL = "/home/div-admin/.dls-keeper/control.sock"


def send_command(cmd: str, quiet: float = 1.5, max_wait: float = 10.0) -> str:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(12)
    try:
        s.connect(CTRL)
    except OSError as e:
        return f"[!] cannot reach keeper: {e}"
    s.sendall(b'{"cmd":"attach"}\n')
    f = s.makefile("rb")
    f.readline()  # attach ack
    s.settimeout(0.0)  # non-blocking reads for collection

    # send the command
    s.sendall(cmd.encode("utf-8", "replace") + b"\n")

    # collect reply until we see the shell prompt ':$ ' or a quiet window.
    # The keeper's reader relays device bytes; the prompt ':/ $ ' signals
    # the command finished.
    buf = b""
    last = time.time()
    deadline = time.time() + max_wait
    saw_prompt = False
    while time.time() < deadline:
        try:
            c = s.recv(65536)
            if c:
                buf += c
                last = time.time()
                if b":/ $" in buf or b"] $ " in buf:
                    saw_prompt = True
                    break
        except BlockingIOError:
            # quiet window after data
            if buf and time.time() - last > quiet and len(buf) > 20:
                break
            time.sleep(0.05)
        except OSError:
            break
    try:
        s.sendall(b"exit\n")
    except OSError:
        pass
    s.close()
    return buf.decode("utf-8", "replace")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "id"
    out = send_command(cmd)
    # strip the "[+] attached..." banner lines
    lines = [ln for ln in out.splitlines() if not ln.startswith(("[+]", "    ", "type commands"))]
    print("\n".join(lines).strip() or "(no output)")