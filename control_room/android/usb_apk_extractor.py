#!/usr/bin/env python3
"""
Andro-DLS — USB APK Extractor

When device is connected via USB cable with debugging enabled,
pull all installed APKs for analysis, binding, or backup.

Usage: python3 modules/usb_apk_extractor.py [-s SERIAL] [-o OUTPUT_DIR]
"""

import subprocess
import os
import sys
import json
from pathlib import Path
from datetime import datetime


def run_adb(*args, serial=None, timeout=30):
    """Run ADB command and return output."""
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", -1


def get_connected_devices():
    """List all connected ADB devices."""
    out, rc = run_adb("devices")
    if rc != 0:
        return []
    devices = []
    for line in out.strip().split("\n")[1:]:  # Skip header
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def get_device_info(serial=None):
    """Get basic device info."""
    info = {}
    props = [
        ("model", "ro.product.model"),
        ("manufacturer", "ro.product.manufacturer"),
        ("android_version", "ro.build.version.release"),
        ("api_level", "ro.build.version.sdk"),
        ("brand", "ro.product.brand"),
        ("cpu_abi", "ro.product.cpu.abi"),
    ]
    for key, prop in props:
        out, _ = run_adb("shell", "getprop", prop, serial=serial)
        info[key] = out
    return info


def list_installed_packages(serial=None, system=False, third_party=True):
    """List installed packages with their APK paths."""
    flags = []
    if third_party:
        flags.append("-3")
    if system:
        flags.append("-s")

    flags.append("-f")  # Show APK path
    out, rc = run_adb("shell", "pm", "list", "packages", *flags, serial=serial)
    if rc != 0:
        return []

    packages = []
    for line in out.strip().split("\n"):
        if line.startswith("package:"):
            # Format: package:/data/app/~~xxx/com.whatsapp-yyy/base.apk=com.whatsapp
            apk_path, pkg_name = line.split("=", 1)
            apk_path = apk_path.replace("package:", "")
            packages.append({
                "name": pkg_name,
                "apk_path": apk_path,
            })
    return packages


def pull_apk(pkg_name, apk_path, output_dir, serial=None):
    """Pull a single APK from device."""
    os.makedirs(output_dir, exist_ok=True)

    # Get file size first
    out, rc = run_adb("shell", "ls", "-l", apk_path, serial=serial)
    size = "unknown"
    if rc == 0:
        parts = out.split()
        if len(parts) >= 5:
            size = parts[4]

    # Pull the APK
    dest = os.path.join(output_dir, f"{pkg_name}.apk")
    out2, rc2 = run_adb("pull", apk_path, dest, serial=serial)

    if rc2 == 0:
        return {
            "package": pkg_name,
            "apk_path": apk_path,
            "dest": dest,
            "size": size,
            "status": "ok",
        }
    else:
        return {
            "package": pkg_name,
            "apk_path": apk_path,
            "dest": dest,
            "size": size,
            "status": f"failed: {out2}",
        }


def pull_split_apk(pkg_name, serial=None):
    """Pull all split APKs for a package (App Bundle / split config)."""
    # Get all APK paths for the package
    out, rc = run_adb("shell", "pm", "path", pkg_name, serial=serial)
    if rc != 0:
        return []

    paths = []
    for line in out.strip().split("\n"):
        if line.startswith("package:"):
            paths.append(line.replace("package:", ""))

    # Also get split paths
    out2, _ = run_adb("shell", "cmd", "package", "list", "splits", pkg_name, serial=serial)
    if out2:
        for line in out2.strip().split("\n"):
            if line.startswith("/"):
                paths.append(line.strip())

    return list(set(paths))  # Deduplicate


def extract_permissions(pkg_name, serial=None):
    """Get all permissions granted/requested by a package."""
    out, rc = run_adb("shell", "dumpsys", "package", pkg_name, serial=serial)
    if rc != 0:
        return {"requested": [], "granted": []}

    requested = []
    granted = []
    in_declared = False
    in_runtime = False

    for line in out.split("\n"):
        if "declared permissions:" in line:
            in_declared = True
            in_runtime = False
            continue
        if "requested permissions:" in line:
            in_declared = False
            in_runtime = True
            continue
        if "install permissions:" in line:
            in_declared = False
            in_runtime = False
            continue
        if "User " in line:
            in_declared = False
            in_runtime = False
            continue

        if in_declared and line.strip().startswith("android.permission."):
            requested.append(line.strip())
        if in_runtime and "granted=true" in line:
            granted.append(line.strip().split(":")[0].strip())

    return {"requested": requested, "granted": granted}


def run_extractor(serial=None, output_dir=None, third_party_only=True, include_splits=False, target_packages=None):
    """Main extraction pipeline."""
    print("=" * 60)
    print("  Andro-DLS — USB APK Extractor")
    print("=" * 60)
    print()

    # Auto-detect device
    if not serial:
        devices = get_connected_devices()
        if not devices:
            print("❌ No device connected. Enable USB debugging and connect via cable.")
            return False
        serial = devices[0]
        print(f"Using device: {serial}")

    # Get device info
    info = get_device_info(serial)
    print(f"Device: {info.get('manufacturer', '?')} {info.get('model', '?')}")
    print(f"Android: {info.get('android_version', '?')} (API {info.get('api_level', '?')})")
    print(f"CPU: {info.get('cpu_abi', '?')}")
    print()

    # Set output directory
    if not output_dir:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"Downloaded-Files/apk_dump_{info.get('model', 'device')}_{ts}"

    os.makedirs(output_dir, exist_ok=True)
    print(f"Output: {output_dir}/")
    print()

    # List packages
    print("[1/3] Scanning installed packages...")
    packages = list_installed_packages(serial, third_party=third_party_only)
    if target_packages:
        packages = [p for p in packages if p["name"] in target_packages]

    print(f"  Found {len(packages)} packages")
    print()

    # Extract
    print("[2/3] Pulling APKs...")
    results = []
    success = 0
    failed = 0

    for i, pkg in enumerate(packages, 1):
        print(f"  [{i}/{len(packages)}] {pkg['name']}...")

        # Pull main APK
        r = pull_apk(pkg["name"], pkg["apk_path"], output_dir, serial)
        results.append(r)

        if r["status"] == "ok":
            success += 1
            print(f"    ✅ {os.path.basename(r['dest'])} ({r['size']} bytes)")
        else:
            failed += 1
            print(f"    ❌ {r['status']}")

        # Pull split APKs if requested
        if include_splits:
            splits = pull_split_apk(pkg["name"], serial)
            for split_path in splits:
                if split_path != pkg["apk_path"]:
                    sr = pull_apk(pkg["name"], split_path, output_dir, serial)
                    if sr["status"] == "ok":
                        print(f"    ✅ split: {os.path.basename(sr['dest'])}")

    print()
    print(f"  Results: {success} pulled, {failed} failed")
    print()

    # Extract permissions for key apps
    print("[3/3] Extracting permissions for sensitive apps...")
    sensitive_apps = [
        "com.whatsapp", "com.telegram.messenger", "com.snapchat.android",
        "com.instagram.android", "com.facebook.katana", "com.google.android.gm",
        "com.viber.voip", "com.skype.raider", "com.zhiliaoapp.musically",
    ]

    perms_output = os.path.join(output_dir, "permissions.json")
    perms_data = {}

    for app in sensitive_apps:
        if any(p["name"] == app for p in packages):
            print(f"  Extracting: {app}")
            perms_data[app] = extract_permissions(app, serial)

    with open(perms_output, "w") as f:
        json.dump(perms_data, f, indent=2)

    print(f"  Permissions saved to: {perms_output}")
    print()

    # Summary
    print("=" * 60)
    print(f"  Extracted {success} APKs to {output_dir}/")
    print(f"  Failed: {failed}")
    print(f"  Permissions data: {perms_output}")
    print("=" * 60)

    return success > 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Andro-DLS USB APK Extractor")
    parser.add_argument("-s", "--serial", help="Device serial")
    parser.add_argument("-o", "--output", help="Output directory")
    parser.add_argument("--all", action="store_true", help="Include system apps")
    parser.add_argument("--splits", action="store_true", help="Include split APKs")
    parser.add_argument("--package", nargs="+", help="Extract specific packages only")
    args = parser.parse_args()

    run_extractor(
        serial=args.serial,
        output_dir=args.output,
        third_party_only=not args.all,
        include_splits=args.splits,
        target_packages=args.package,
    )
