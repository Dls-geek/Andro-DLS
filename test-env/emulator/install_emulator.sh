#!/bin/bash
# install_emulator.sh - Installs latest Android Emulator (API 34)
echo "[*] Checking system environment..."

# Check Java
if ! command -v java &> /dev/null; then
    echo "[!] Java not found. Installing OpenJDK 17..."
    sudo apt-get update && sudo apt-get install openjdk-17-jdk -y
fi

# Install dependencies
echo "[*] Installing required packages..."
sudo apt-get install -y libglu1-mesa libx64-64 libxtst6 wget unzip

# Download Android Command-Line Tools
echo "[*] Downloading Android SDK tools..."
mkdir -p ~/Android/Sdk/cmdline-tools/latest/bin
cd /tmp
wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O cmdline-tools.zip
unzip cmdline-tools.zip -d /tmp/cmdline-tools
cp -r /tmp/cmdline-tools/cmdline-tools ~/Android/Sdk/cmdline-tools/

# Accept licenses
yes | ~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --licenses > /dev/null
yes | ~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager "platform-tools" "platforms;android-34" "emulator" "system-images;android-34;google_apis;x86_64" > /dev/null

echo "[*] Android SDK installed successfully!"
echo "[*] Creating AVD named 'androdls_test'..."
yes | ~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager "ndk;25.2.9477393" 2>/dev/null

# Create AVD
echo "no" | ~/Android/Sdk/cmdline-tools/latest/bin/avdmanager create avd -n androdls_test -k "system-images;android-34;google_apis;x86_64" --force

echo "[*] AVD created. Starting emulator in background..."
nohup ~/Android/Sdk/emulator/emulator -avd androdls_test -no-snapshot-save -no-audio > /tmp/emulator.log 2>&1 &
sleep 10

echo "[*] Emulator should now boot. Waiting for device..."
~/Android/Sdk/platform-tools/adb wait-for-device shell 'while [[ -z $(getprop sys.boot_completed) ]]; do sleep 1; done; echo boot_complete'

echo "[✅] Android Emulator (API 34) is ready!"