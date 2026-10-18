#!/usr/bin/env python3
"""
patch_targetsdk.py — bump targetSdkVersion of an msfvenom Android payload APK
so modern Android (14/15, API 34+) accepts the install.

Method: byte-level patch of the binary AndroidManifest.xml INSIDE the APK
(targetSdkVersion attribute 0x0101021c, TYPE_INT_DEC value 17 -> 34), then
re-zip. Signing is a separate step (apksigner).

Usage:
    python patch_targetsdk.py test.apk test-fixed.apk [NEW_TARGET_SDK]
"""
import shutil
import sys
import zipfile

ATTR_TARGET_SDK = b"\x1c\x02\x01\x01"  # 0x0101021c little-endian


def patch_manifest(data: bytes, new_sdk: int) -> tuple[bytes, int]:
    """Patch targetSdkVersion int values. Returns (new_bytes, patches_applied)."""
    patches = 0
    out = bytearray(data)
    i = 0
    while True:
        idx = out.find(ATTR_TARGET_SDK, i)
        if idx == -1:
            break
        # attribute entry: ns(4) name(4) rawValue(4) typed{size(1) res0(1) type(1) data(4)}
        if idx + 16 <= len(out) and out[idx + 8 : idx + 8 + 3] == b"\x08\x00\x10":
            old = int.from_bytes(out[idx + 12 : idx + 16], "little")
            if old != new_sdk:
                out[idx + 12 : idx + 16] = new_sdk.to_bytes(4, "little")
                patches += 1
                print(f"  patched targetSdkVersion {old} -> {new_sdk} @ offset {idx}")
            else:
                print(f"  targetSdkVersion already {new_sdk} @ offset {idx}")
        i = idx + 4
    return bytes(out), patches


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    new_sdk = int(sys.argv[3]) if len(sys.argv) > 3 else 34

    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        if "AndroidManifest.xml" not in names:
            print("ERROR: AndroidManifest.xml not found in APK")
            return 1
        manifest = zin.read("AndroidManifest.xml")

    print(f"Patching {src} -> {dst} (targetSdk {new_sdk})")
    new_manifest, n = patch_manifest(manifest, new_sdk)
    if n == 0:
        print("WARNING: no targetSdkVersion int attribute patched — check AXML format")

    with zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "AndroidManifest.xml":
                data = new_manifest
                item.compress_type = zipfile.ZIP_STORED  # manifest stored, like aapt does
            zout.writestr(item, data)
    print(f"Wrote {dst} with patched manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())