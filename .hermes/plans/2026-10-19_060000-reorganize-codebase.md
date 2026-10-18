# Andro-DLS Codebase Reorganization Plan

> **For Hermes:** Use plan skill — review with Captain before executing.
> **Date:** 2026-10-19
> **Goal:** Reorganize sprawling codebase into a clean 5-part structure

---

## Current Problem

```
Andro-DLS/ (root — 40+ loose files)
├── androdls.py          ← CLI, root
├── bind_payload.sh      ← build script, root
├── deploy_agent.sh      ← deploy script, root
├── dls-keeper.service   ← systemd unit, root
├── apktool.jar          ← tool, root
├── debug.keystore       ← key, root
├── scrcpy*              ← tool binary, root
├── agent/               ← v10 agent Java
├── agent-enhanced/      ← v3 agent (latest)
├── payload/             ← v1 agent (deprecated)
├── .payload-build/      ← build artifacts
├── modules/             ← 40 Python modules
├── pipeline/            ← pipeline configs
├── docs/                ← documentation
├── Downloaded-Files/    ← exfiltrated data
├── god phone taker/     ← Windows GUI
└── landing/             ← ??
```

**Problems:**
- 40+ files at root — no one knows where anything is
- 3 different agent versions in 3 different dirs
- Python modules flat in `modules/` — no sub-grouping
- Build scripts scattered across root
- Exfiltrated data mixed with source code
- Tools (scrcpy, apktool.jar) in root

---

## Target Architecture

```
Andro-DLS/
│
├── control-room/                  # 1️⃣ Control Room
│   ├── cli/                       # CLI interface
│   │   ├── androdls.py            # Main entry point
│   │   ├── banner.py
│   │   ├── autoflow.py
│   │   ├── pentest.py
│   │   └── watchdog_menu.py
│   ├── c2-server/                 # C2 HTTP listener
│   │   ├── c2_server.py           # Interactive C2 server v3
│   │   ├── c2_send.py
│   │   └── README.md
│   ├── keeper/                    # Tunnel/keeper daemon
│   │   ├── keeper.py
│   │   ├── keeper_cmd.py
│   │   ├── internet_ctrl.py
│   │   ├── tunnel.py
│   │   └── dls-keeper.service
│   ├── core/                      # Shared utilities
│   │   ├── communication.py
│   │   ├── connection.py
│   │   ├── config.py
│   │   ├── device.py
│   │   ├── devices.py
│   │   └── phones.py
│   ├── ops/                       # Operational modules
│   │   ├── app_manager.py
│   │   ├── data_extraction.py
│   │   ├── file_manager.py
│   │   ├── full_access.py
│   │   ├── input_control.py
│   │   ├── media.py
│   │   ├── remoteshell.py
│   │   └── shell_access.py
│   ├── net/                       # Network modules
│   │   ├── wifi_utils.py
│   │   ├── port_forward.py
│   │   ├── pivot.py
│   │   └── reaccess.py
│   ├── android/                   # Android-specific
│   │   ├── usb_apk_extractor.py
│   │   ├── usb_permissions.py
│   │   ├── root_check.py
│   │   └── work_profile.py
│   ├── security.py
│   ├── extras.py
│   └── README.md                  # Control room docs
│
├── test-env/                      # 2️⃣ Test Environment
│   ├── emulator/
│   │   ├── install_emulator.sh
│   │   └── test_emulator.sh
│   ├── adb
│   ├── scrcpy
│   ├── scrcpy-server
│   ├── scrcpy.1
│   └── README.md
│
├── payloads/                       # 3️⃣ Payloads
│   ├── androdls-v3/               # Latest agent (from agent-enhanced/)
│   │   ├── src/com/androdls/
│   │   │   ├── Agent.java         # Main agent: camera, mic, dumps, XOR
│   │   │   ├── MainActivity.java
│   │   │   └── BootReceiver.java
│   │   ├── res/
│   │   ├── AndroidManifest.xml
│   │   ├── build.sh               # One-shot build
│   │   └── README.md              # Agent capabilities doc
│   ├── inshot-bind/               # InShot trojan binding
│   │   ├── bind_payload.sh
│   │   ├── apktool.jar
│   │   └── README.md
│   ├── stage1/                    # Stage-1 payloads (shell)
│   ├── stage2/                    # Stage-2 payloads (Meterpreter stubs)
│   ├── artifacts/                 # Built APKs (not in git if gitignored)
│   │   ├── agent-v3.apk
│   │   ├── emulator-v1.apk
│   │   └── test-builds/
│   ├── debug.keystore
│   └── README.md                  # Full payload documentation
│
├── legacy/                        # 4️⃣ Legacy (preserved, not deleted)
│   ├── v10-agent/                 # Old PhoneSploit agent
│   │   ├── AgentCore.java
│   │   ├── AgentShell.java
│   │   ├── BootReceiver.java
│   │   ├── DlsLauncher.java
│   │   ├── DlsService.java
│   │   ├── PowerReceiver.java
│   │   ├── ResurrectionJob.java
│   │   ├── UserPresentReceiver.java
│   │   └── WatchdogReceiver.java
│   ├── v1-agent/                  # Deprecated v1 payload
│   │   ├── src/com/androdls/
│   │   └── AndroidManifest.xml
│   ├── old-builds/                # .payload-build/ artifacts
│   └── README.md
│
├── docs/                          # 5️⃣ Documentation
│   ├── HANDOFF.md
│   ├── ROADMAP.md
│   ├── progress_log.md
│   ├── TEST_REPORT.md
│   ├── OPS_GUIDE.md
│   ├── analysis/
│   │   ├── inshot-trojan-analysis.md
│   │   └── kernel-persistence-roadmap.md
│   └── images/
│
├── pipeline/                      # Pipeline configs (keep as-is)
│   ├── handler-http.rc
│   ├── handler-interactive.rc
│   ├── handler.rc
│   ├── handler-stageless.rc
│   ├── README_pipeline.md
│   └── SELF_GUIDE_pipeline.md
│
├── exfil-data/                    # Exfiltrated data (renamed)
│   └── Device-Name/
│       ├── Audio/
│       ├── Data-Dumps/
│       ├── Screenshots/
│       └── Downloads/
│
├── tools/                         # External tools
│   ├── god-phone-taker/           # Windows GUI
│   ├── auto_pivot.py
│   ├── patch_targetsdk.py
│   └── landing/
│
├── scripts/                       # Root-level build/deploy scripts
│   ├── build_agent_pure.sh
│   ├── build_payload_enhanced.sh
│   └── deploy_agent.sh
│
├── .github/
├── .venv/
├── icon.png
├── requirements.txt
├── README.md
├── CONTRIBUTING.md
├── LICENSE
├── install.sh
└── .gitignore
```

---

## Step-by-Step Plan

### Phase 1: Create Target Structure (no moves yet)

**Task 1.1: Create all directories**
```bash
mkdir -p control-room/{cli,c2-server,keeper,core,ops,net,android}
mkdir -p test-env/emulator
mkdir -p payloads/{androdls-v3/src/com/androdls,inshot-bind,stage1,stage2,artifacts}
mkdir -p legacy/{v10-agent,v1-agent/src/com/androdls,old-builds}
mkdir -p docs/analysis
mkdir -p exfil-data
mkdir -p tools/god-phone-taker
mkdir -p scripts
```

### Phase 2: Move Files (by section)

**Task 2.1: Control Room → control-room/**
| From | To |
|------|-----|
| `modules/autoflow.py` | `control-room/cli/autoflow.py` |
| `modules/pentest.py` | `control-room/cli/pentest.py` |
| `modules/banner.py` | `control-room/cli/banner.py` |
| `modules/watchdog_menu.py` | `control-room/cli/watchdog_menu.py` |
| `androdls.py` | `control-room/cli/androdls.py` |
| `modules/keeper.py` | `control-room/keeper/keeper.py` |
| `modules/keeper_cmd.py` | `control-room/keeper/keeper_cmd.py` |
| `modules/internet_ctrl.py` | `control-room/keeper/internet_ctrl.py` |
| `modules/tunnel.py` | `control-room/keeper/tunnel.py` |
| `dls-keeper.service` | `control-room/keeper/dls-keeper.service` |
| `modules/communication.py` | `control-room/core/communication.py` |
| `modules/connection.py` | `control-room/core/connection.py` |
| `modules/config.py` | `control-room/core/config.py` |
| `modules/device.py` | `control-room/core/device.py` |
| `modules/devices.py` | `control-room/core/devices.py` |
| `modules/phones.py` | `control-room/core/phones.py` |
| `modules/app_manager.py` | `control-room/ops/app_manager.py` |
| `modules/data_extraction.py` | `control-room/ops/data_extraction.py` |
| `modules/file_manager.py` | `control-room/ops/file_manager.py` |
| `modules/full_access.py` | `control-room/ops/full_access.py` |
| `modules/input_control.py` | `control-room/ops/input_control.py` |
| `modules/media.py` | `control-room/ops/media.py` |
| `modules/remoteshell.py` | `control-room/ops/remoteshell.py` |
| `modules/shell_access.py` | `control-room/ops/shell_access.py` |
| `modules/wifi_utils.py` | `control-room/net/wifi_utils.py` |
| `modules/port_forward.py` | `control-room/net/port_forward.py` |
| `modules/pivot.py` | `control-room/net/pivot.py` |
| `modules/reaccess.py` | `control-room/net/reaccess.py` |
| `modules/usb_apk_extractor.py` | `control-room/android/usb_apk_extractor.py` |
| `modules/usb_permissions.py` | `control-room/android/usb_permissions.py` |
| `modules/root_check.py` | `control-room/android/root_check.py` |
| `modules/work_profile.py` | `control-room/android/work_profile.py` |
| `modules/security.py` | `control-room/security.py` |
| `modules/extras.py` | `control-room/extras.py` |
| `modules/cli.py` | `control-room/cli/cli.py` |
| `modules/console.py` | `control-room/cli/console.py` |
| `modules/tools.py` | `control-room/cli/tools.py` |
| `agent-enhanced/c2_server.py` | `control-room/c2-server/c2_server.py` |
| `agent-enhanced/c2_send.py` | `control-room/c2-server/c2_send.py` |
| `payload/c2_server.py` | `control-room/c2-server/c2_server_v1.py` (rename) |

**Task 2.2: Test Environment → test-env/**
| From | To |
|------|-----|
| `payload/install_emulator.sh` | `test-env/emulator/install_emulator.sh` |
| `test_emulator.sh` | `test-env/emulator/test_emulator.sh` |
| `adb` | `test-env/adb` |
| `scrcpy` | `test-env/scrcpy` |
| `scrcpy-server` | `test-env/scrcpy-server` |
| `scrcpy.1` | `test-env/scrcpy.1` |

**Task 2.3: Payloads → payloads/**
| From | To |
|------|-----|
| `agent-enhanced/src/` | `payloads/androdls-v3/src/` |
| `agent-enhanced/res/` | `payloads/androdls-v3/res/` |
| `agent-enhanced/AndroidManifest.xml` | `payloads/androdls-v3/AndroidManifest.xml` |
| `agent-enhanced/build.sh` | `payloads/androdls-v3/build.sh` |
| `agent-enhanced/agent.apk` | `payloads/artifacts/agent-v3.apk` |
| `bind_payload.sh` | `payloads/inshot-bind/bind_payload.sh` |
| `apktool.jar` | `payloads/inshot-bind/apktool.jar` |
| `debug.keystore` | `payloads/debug.keystore` |
| `androdls-emulator.apk` | `payloads/artifacts/emulator-v1.apk` |
| `androdls-test.apk` | `payloads/artifacts/test-builds/androdls-test.apk` |

**Task 2.4: Legacy → legacy/**
| From | To |
|------|-----|
| `agent/*.java` | `legacy/v10-agent/` |
| `payload/src/` | `legacy/v1-agent/src/` |
| `payload/AndroidManifest.xml` | `legacy/v1-agent/AndroidManifest.xml` |
| `payload/build_payload.sh` | `legacy/v1-agent/build_payload.sh` |
| `.payload-build/` | `legacy/old-builds/` |

**Task 2.5: Docs → docs/**
| From | To |
|------|-----|
| `ROADMAP.md` | `docs/ROADMAP.md` |
| `progress_log.md` | `docs/progress_log.md` |
| `TEST_REPORT.md` | `docs/TEST_REPORT.md` |
| `OPS_GUIDE.md` | `docs/OPS_GUIDE.md` |
| `docs/inshot-trojan-analysis.md` | `docs/analysis/inshot-trojan-analysis.md` |
| `docs/kernel-persistence-roadmap.md` | `docs/analysis/kernel-persistence-roadmap.md` |

**Task 2.6: Exfil Data → exfil-data/**
```bash
mv "Downloaded-Files" exfil-data/devices
```

**Task 2.7: Tools → tools/**
| From | To |
|------|-----|
| `god phone taker/` | `tools/god-phone-taker/` |
| `auto_pivot.py` | `tools/auto_pivot.py` |
| `patch_targetsdk.py` | `tools/patch_targetsdk.py` |
| `landing/` | `tools/landing/` |

**Task 2.8: Scripts → scripts/**
| From | To |
|------|-----|
| `build_agent_pure.sh` | `scripts/build_agent_pure.sh` |
| `build_payload_enhanced.sh` | `scripts/build_payload_enhanced.sh` |
| `deploy_agent.sh` | `scripts/deploy_agent.sh` |
| `install.sh` | `scripts/install.sh` |

### Phase 3: Fix Imports

**Task 3.1: Fix Python imports**
All `from modules.xxx import yyy` → update to new paths:
- `from modules.keeper import` → `from control_room.keeper.keeper import`
- `from modules.internet_ctrl import` → `from control_room.keeper.internet_ctrl import`
- etc.

Run: `grep -r "from modules\." control-room/` to find all

**Task 3.2: Fix `androdls.py` and `cli.py`**
Main CLI imports modules — need full import path audit.

**Task 3.3: Fix `build.sh` paths**
`agent-enhanced/build.sh` moved to `payloads/androdls-v3/build.sh` — relative paths need updating.

**Task 3.4: Fix `dls-keeper.service`**
Update `ExecStart` to new path.

### Phase 4: Create READMEs

**Task 4.1: Root README.md**
Rewrite with new structure map.

**Task 4.2: Section READMEs**
Each top-level dir gets a README:
- `control-room/README.md` — how to start C2, CLI, keeper
- `test-env/README.md` — emulator setup
- `payloads/README.md` — all payloads, capabilities, build instructions
- `payloads/androdls-v3/README.md` — agent capabilities, commands, permissions
- `legacy/README.md` — what's preserved, why

### Phase 5: Verify & Commit

**Task 5.1: Verify CLI still works**
```bash
cd control-room/cli && python androdls.py --help
```

**Task 5.2: Verify C2 server starts**
```bash
cd control-room/c2-server && timeout 3 python c2_server.py || true
```

**Task 5.3: Verify agent builds**
```bash
cd payloads/androdls-v3 && bash build.sh
```

**Task 5.4: Git commit**
```bash
git add -A
git commit -m "refactor: reorganize codebase into 5-section structure

- control-room/: CLI, C2 server, keeper, all Python modules
- test-env/: emulator, ADB, scrcpy
- payloads/: agents, binding tools, artifacts
- legacy/: v10 agent, v1 agent, old builds
- docs/: all documentation consolidated
- exfil-data/: exfiltrated device data
- tools/: external tools
- scripts/: build/deploy helpers"
```

---

## What Doesn't Move

| Item | Reason |
|------|--------|
| `.git/` | Git internals |
| `.venv/` | Virtual env — stays at root |
| `.github/` | GitHub CI/templates |
| `.gitignore` | Root config |
| `requirements.txt` | Root — shared across project |
| `pipeline/` | Stays as-is (handler configs) |
| `icon.png` | Repo icon |
| `LICENSE` | Root |
| `CONTRIBUTING.md` | Root |
| `SECURITY.md` on `docs/` | Deleted/moved |
| `__pycache__/` dirs | Ignored, cleaned |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Python imports break | `grep -r "from modules"` audit before commit |
| build.sh relative paths break | Test build after move |
| keeper.service path wrong | Update ExecStart, reload systemd |
| CLI `androdls.py` can't find modules | Add `sys.path` adjustment or use package imports |

---

## Estimated Time

- Phase 1 (dirs): 2 min
- Phase 2 (moves): 5 min
- Phase 3 (import fixes): 10 min
- Phase 4 (READMEs): 5 min
- Phase 5 (verify): 5 min
- **Total: ~30 min**