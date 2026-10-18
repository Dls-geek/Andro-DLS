#!/usr/bin/env bash
# build.sh — One-shot: compile → dex → APK → sign → install
# Usage: ./build.sh [C2_IP] [C2_PORT]
# Default: 100.68.158.25:8080

set -euo pipefail

C2_IP="${1:-100.68.158.25}"
C2_PORT="${2:-8080}"
OUT="agent.apk"

SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
BT="$SDK/build-tools/35.0.0"
ANDROID_JAR="$SDK/platforms/android-35/android.jar"
JH="${JAVA_HOME:-/home/div-admin/.local/jdk-17}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/src/com/androdls"
BUILD="$ROOT/.build"
GEN="$BUILD/gen/classes"
DEX_DIR="$BUILD/gen/dex"
APK_BUILD="$BUILD/apk"

echo "[*] Cleaning…"
rm -rf "$BUILD"
mkdir -p "$GEN" "$DEX_DIR" "$APK_BUILD"

# Patch C2 IP in Agent.java
AGENT_JAVA="$SRC/Agent.java"
sed -i "s|C2_BASE = \"http://[^\"]*\"|C2_BASE = \"http://${C2_IP}:${C2_PORT}\"|" "$AGENT_JAVA"

echo "[1/6] Compiling Java → .class…"
"$JH/bin/javac" -source 8 -target 8 -classpath "$ANDROID_JAR" \
    -d "$GEN" "$SRC"/*.java 2>&1

echo "[2/6] .class → classes.dex…"
"$BT/d8" --lib "$ANDROID_JAR" --output "$DEX_DIR" "$GEN/com/androdls/"*.class \
    --min-api 26 2>&1

echo "[3/6] Building APK structure…"
cp "$ROOT/AndroidManifest.xml" "$APK_BUILD/"
"$BT/aapt2" compile -o "$APK_BUILD/res.zip" --dir "$ROOT/res/" 2>&1
"$BT/aapt2" link "$APK_BUILD/res.zip" \
    -I "$ANDROID_JAR" \
    --manifest "$APK_BUILD/AndroidManifest.xml" \
    --min-sdk-version 26 \
    --target-sdk-version 35 \
    -o "$APK_BUILD/base.apk" 2>&1

# Add classes.dex to the APK
cp "$DEX_DIR/classes.dex" "$APK_BUILD/"
cd "$APK_BUILD" && zip -q base.apk classes.dex && cd "$ROOT"

echo "[4/6] Zipalign…"
"$BT/zipalign" -f 4 "$APK_BUILD/base.apk" "$APK_BUILD/aligned.apk"

echo "[5/6] Signing…"
"$BT/apksigner" sign \
    --ks "$HOME/.android/debug.keystore" \
    --ks-pass pass:android \
    --key-pass pass:android \
    --out "$OUT" "$APK_BUILD/aligned.apk" 2>&1

echo "[6/6] Installing…"
adb install -r "$OUT" 2>/dev/null || echo "⚠ No device connected; APK at $OUT"

echo "[+] Done: $(ls -lh "$OUT" | awk '{print $5}')"
adb shell am start -n com.androdls/.MainActivity 2>/dev/null || true