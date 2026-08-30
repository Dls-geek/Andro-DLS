#!/usr/bin/env bash
# install.sh — install dls-keeper as a systemd USER service with linger,
# so the tunnel+listener survive reboot and run 24/7 without login.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${DLS_PYTHON:-$HOME/.venv/bin/python}"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/dls-keeper.service"

[ -x "$PY" ] || PY="$(command -v python3)"

mkdir -p "$UNIT_DIR"

cat > "$UNIT" <<EOF
[Unit]
Description=DLS Keeper 24/7 (portmap tunnel + payload shell listener)
Documentation=file://$ROOT/HANDOFF.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$PY $ROOT/modules/keeper.py daemon
Restart=always
RestartSec=5
Environment=DLS_LPORT=4445
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

echo "[*] unit written: $UNIT"
systemctl --user daemon-reload
systemctl --user enable dls-keeper.service >/dev/null
echo "[*] enabling linger (survive logout/reboot)..."
if ! loginctl enable-linger "$USER" 2>/dev/null; then
    echo "[!] enable-linger needed sudo — trying with sudo"
    sudo loginctl enable-linger "$USER" || echo "[!!] could not enable linger — keeper will only run while logged in"
fi
systemctl --user restart dls-keeper.service
sleep 2
systemctl --user --no-pager status dls-keeper.service | head -12
echo ""
echo "[✓] installed.  CLI option 66 = Watchdog menu · keeper.py status · journalctl --user -u dls-keeper -f"
