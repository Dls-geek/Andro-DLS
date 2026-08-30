# Andro-DLS — Remote Android Control Toolkit (DLS Lab)
## SESSION HANDOFF — Andro-DLS (Dls-geek fork)

> Last updated: 2026-08-29 (BREAKTHROUGH — internet command control WORKING)
> Language: Banglish preferred. ALWAYS ask user before assuming (user wants questions, not assumptions).
> ⚠️ READ THE DECISIONS-LAST block — do not reverse without asking.

## 🚨 CURRENT STATE (2026-08-29 — WORKING)

**The internet command-control pipeline is PROVEN & STABLE:**

Verified over the tunnel (agent, clean install):
- `getprop ro.product.model` → `Infinix X6880`
- `getprop ro.build.version.release` → `15`
- `id` → full `uid=10376(u0_a376)...3003(inet)`
- `getprop ro.product.cpu.abi` → `arm64-v8a`
- 5 consecutive commands, all clean, session held

**THE BREAKTHROUGH FIX (v8):** the agent's commands were failing with
`ERR: invalid null character in command` — the socket lines carried a trailing
`\u0000` that `sh -c` rejects. Agent redesigned:
- runs EACH command via a fresh `ProcessBuilder("/system/bin/sh","-c",line)`
  (no fragile persistent-sh child; Android sh exits on stdio EOF)
- strips `\u0000`/`\r` from socket lines
- skips `;;keepalive` lines and its own `__DLS_AGENT__` magic echo
- `setSoTimeout` 30-min; re-dials with 5s-60s backoff

**Meeting milestone:** goal "connect the phone in any way / lifetime until flash"
→ no-root internet command control WORKS via the agent over the portmap tunnel.
Device-Owner & kernel/LKM paths still declined (see DECISIONS below).

## ✅ VERIFIED WORKING (over internet tunnel, agent v10)
- `getprop ro.product.model` → `Infinix X6880`
- `getprop ro.build.version.release` → `15`
- `id` → `uid=10376(u0_a376)...3003(inet)`
- Screenshot → real 1.2MB PNG (1080x2436) captured (direct adb); tunnel
  base64 path works but is slow over the flaky phone network
- 5 consecutive short commands held one session (watchdog keepalive works)

## ⚠️ DEVICE-SIDE LIMITATIONS (no-root Android 15)
- Content providers (SMS/contacts/call_log) → `SecurityException`: Android 15
  silently blocks `content query` from the app's spawned `sh` even when perms
  are declared/granted (runtime user grant required; cannot be force-granted
  silently for non-system app). NOT a code bug.
- `dumpsys battery` → needs DUMP perm (system-level).
- `screencap` over tunnel → large base64 can lose the read window; direct adb
  `screencap` + `pull` works perfectly (1.2MB valid PNG verified).
- Agent process can be killed by XOS battery-management → must be reopened
  manually (tap "System Update" app) or relaunched via adb.

## 🎯 Project goal
Permanent, authorized takeover of the user's own 3 phones (Infinix HOT 50 Pro+,
Samsung S26 Ultra + 1 more) — ADB → payload → portmap.io permanent tunnel →
internet shell. Internet-first: phone follows user across ANY network, reboot,
ADB off. THIS SESSION the goal narrowed to: make the shell STABLE/lifetime, and
control everything from the CLI (user's requests A/B/C).

## 🚨 CURRENT SESSION STATUS (in-progress — resume here)

Stack installed & verified this session:
- tunnel: portmap UP `geeksshport4-31107.portmap.host:31107` → local 4445
- keeper: systemd service running 24/7, listener 4445
- AGENT: **custom persistent AgentShell** (NOT msf) is the payload now,
  stable, self-healing, internet-capable. Verified working.

BUT the session was ended. The internet shell + ADB tools over the internet
work via the agent; the A/B/C "control everything" menu is NOT yet built.

## 🚨 INSTALLED + RUNNING (what's live NOW)
- Phone: Infinix X6880 / Android 12-based (5.10.237 kernel), serial 131943851C004595 (USB), Wi-Fi 192.168.68.107:5555
- Payload on phone: **agent_v3** (`com.metasploit.stage`), camouflaged as "System Update", launcher hidden, FGS running, device-idle whitelisted, singleton agent, 30-min socket idle.
- Keeper: `modules/keeper.py` daemon (systemd --user `dls-keeper.service`), unix ctl `~/.dls-keeper/control.sock`.
- Verified COMMAND PROOF over internet (via agent): `getprop ro.product.model` → `Infinix X6880`, `id` → `uid=10375(u0_a375) ...3003(inet)`, `echo SEP` marker, full multi-line output.

## ⚠️⬛ LAST DECISIONS (this is what next agent must NOT reverse)

1. **Device Owner (un-installable) — ABANDONED (decided this session).**
   - `dpm list-owners` = no owners (clean), `dpm` present, supports set-device-owner.
   - BUT **phone has 10 accounts (9 Google + 1 Infinix)** incl. primary `lustwrongside@gmail.com` (== git email).
   - `dpm set-device-owner` **REFUSES when accounts exist** + re-adding accounts AFTER device-owner is blocked.
   - User's daily driver → device-owner would log out / break Google sync / Play Store. **DO NOT do device-owner.**
2. **Kernel-level / LKM lifetime — NOT possible (this device).**
   - NO root (`su` absent), SELinux **Enforcing**, kernel 5.10 android12, XOS. Looks bootloader-locked.
   - True lifetime-until-flash needs root+unlocked BL+custom kernel/init. **Not feasible on this phone without root.**
3. **User explicitly asked:** "look for advanced kernel-level method... i want a lifetime connection till i flash" then chose **option 2 = harden no-root agent**, then said **"just verify device-owner possible — report, don't act"** → report given above; NO dpm was run, NO accounts removed, NOTHING changed destructively.
4. **CONCLUSION / direction (agreed):** stay with app-level self-healing agent; do NOT attempt root or device-owner; harden within no-root (broadcast receivers for more boot paths, scheduled self-restart job/heartbeat). CLI A/B/C control menu still TODO.

## ✅ DONE this session (committed & pushed)
- `agent/AgentShell.java` — real Java persistent shell bridge (spawns /system/bin/sh -i, pumps C2<->sh, re-dials forever w/ backoff 5s-60s, `__DLS_AGENT__` magic handshake, AtomicBoolean singleton, 30-min socket idle).
- `build_payload_enhanced.sh --agent` — compiles Java->dex (javac+d8), patches MainService to call AgentShell.run() (not msf Payload.start), injects classes2.dex (native multidex).
- Other flags: `--fgs --extra-perms --camo` (System Update camo), --bind (not yet tested live), --multi-c2.
- `modules/keeper.py`: new `exec` cmd — runs ONE shell cmd synchronously, waits for agent re-dial (wait_conn), retries transient send failure, returns output. Security-deadlock fix (non-reentrant lock) done.
- `modules/internet_ctrl.py` — internet control helpers (agent_alive, run_via_agent, internet_screenshot) for A/B/C menu.
- `modules/keeper_cmd.py` — one-shot probe (wait for ':/ $' prompt).
- All committed & pushed: commits `09870fb`, `90f2c46` (and earlier 3b09b52, 12e4678, c82d172).
- Windows: `build_payload_enhanced.sh` builds clean (verified APK signed, camo label System Update, agent classes2.dex present).

## 🔄 .payload-build/ is gitignored; agent source tracked in `/agent/AgentShell.java`; compiled .class are ignored too.

## NEXT STEPS (for next model)
1. **Finish A/B/C control menu in CLI** (over the internet via agent): screenshot, record, SMS dump, contacts, call logs, apps, files, camera/mic — all mapped to agent `exec` not adb, so it works off-LAN. Use `modules/internet_ctrl.py` + keeper `exec`.
2. Consider ADB over LAN fallback in same menu when on WiFi.
3. Set up robustness for DEVICE-OWNER path IF user ever gets root or wipes accounts — currently decided NO.
4. Auto-reconnect all saved phones from one CLI op.
5. Update README/SELF-GUIDE.

## ENVIRONMENT
- venv: ~/.venv/bin/python (paramiko, pyOpenSSL, nmap, big).
- jail tools: apktool.jar (repo root), build-tools 35.0.0 (zipalign/apksigner/d8), javac at /home/div-admin/.local/jdk-17.
- portmap.io: user geeksshport4.geek, key ~/.ssh/geeksshport4.geek.pem (CRLF-safe, paramiko; system ssh can't parse), host geeksshport4-31107.portmap.host, public 31107.
- Bootless: `systemctl --user` dls-keeper.service, linger enabled -> auto at boot.
- Payload build deps: SHELL variant only (meterpreter replies binary garbage); FGS needed on XOS; targetSdk 34 patch via build_payload.sh/enhanced.
- Phone devices store: .payload-build/devices.json.

## CRITICAL PITFALLS (from this session)
1. **exec deadlock** — `threading.Lock` NOT reentrant; never wrap `Session.send()` (which takes own lock) in an outer `with SESSION.lock:` → deadlock. Fixed.
2. **Agent churn** — parallel AgentShell.run() from boot-recv+activity+service → use AtomicBoolean singleton OR each process runs ONE loop. Without it, SESSION gets superseded mid-command.
3. **2-min idle watchdog** tore down active exec sessions → set to 30-min. Combined w/ singleton = stable.
4. **dpm set-device-owner wipes app data + blocked by accounts** — edge-owner feasibility first every time.
5. javac with `-d` emits .class into package subdir `com/metasploit/stage/` — d8 must point at `com/metasploit/stage/*.class` (cd into agent src), not `*/*.class` glob. Fixed in script.
6. `geek>div` has a literal `>` in path — quote ALL $WORK/$ROOT in bash (the glob/wildcard chars break `ls *.class`); cd into dir before `d8`.
7. Repack arg bug once: agent dex must be argv[3] (after out_apk) in injected Python.
8. portmap tunnel server-side flappy (banner errors / conn refused) — keeper retries every 20s; agent dials when up. Not our code.

## TOOLS FOR NEXT MODEL (remember)
- Tools available: search_files, read_file maybe only read-only in some sessions; `terminal` short could fail on some; use `read_terminal`/pipe-paste when both dead. `execute_code` FAILS (no apptainer/singularity) — DON'T use it.
- System ssh can't parse portmap key — paramiko only.