# pipeline/ — scripts & handlers (legacy + helpers)

> **Primary path is the CLI**: `androdls.py` → options **64** (Full Access),
> **65** (Auto-Pivot), **66** (Portmap setup). Python logic lives in
> `modules/remoteshell.py`, `modules/tunnel.py`, `modules/pivot.py`,
> `modules/full_access.py`, `modules/shell_access.py`.

| File | Status | Notes |
|---|---|---|
| `psp_pipeline.sh` | legacy | bash orchestration (usb/remote/status/cleanup) |
| `auto_pivot.py` | legacy | earlier USB→Wi-Fi pivot (superseded by option 65) |
| `auto_pivot_auto.py` | legacy | zero-input variant (superseded by option 65) |
| `handler*.rc` | helper | msfconsole resource files (optional; pure-Python listener preferred) |
| `SELF-GUIDE.md` | docs | manual walkthrough incl. internet remote access |

Keep these for reference / manual operations. Day-to-day: use the CLI menu.