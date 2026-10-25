#!/usr/bin/env python3
"""Stage a deterministic ZIP and external catalog fragment; never publish."""
import argparse
import hashlib
import json
import pathlib
import platform
import sys
import stat
import subprocess
import zipfile

TARGETS = {"aarch64-apple-darwin": "tezbar-color-picker", "x86_64-pc-windows-msvc": "tezbar-color-picker.exe"}
ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()



def validate_sampler(data):
    assert data[:8] == b"\xcf\xfa\xed\xfe\x0c\x00\x00\x01", "Sampler must be Mach-O ARM64"
    offset = 32
    for _ in range(int.from_bytes(data[16:20], "little")):
        command = int.from_bytes(data[offset:offset+4], "little")
        size = int.from_bytes(data[offset+4:offset+8], "little")
        assert size >= 8 and offset + size <= len(data), "Invalid Mach-O load command"
        if command == 0x32:  # LC_BUILD_VERSION
            platform_id = int.from_bytes(data[offset+8:offset+12], "little")
            minimum = int.from_bytes(data[offset+12:offset+16], "little")
            assert platform_id == 1 and minimum == 11 << 16, "Build the sampler for macOS 11.0, not the build machine's OS"
            return
        offset += size
    raise AssertionError("Sampler has no macOS deployment target")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--binary", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "dist")
    args = parser.parse_args()
    assert (sys.platform, platform.machine().lower()) in (
        [("darwin", "arm64")] if args.target == "aarch64-apple-darwin" else [("win32", "amd64")]
    ), "Package on the declared native target runner"
    manifest = json.loads((ROOT / "extension.json").read_text(encoding="utf-8"))
    # Run the actual built target on its native runner before packaging.
    info = json.loads(subprocess.check_output([str(args.binary.resolve()), "--protocol-info"], timeout=5))
    assert info["id"] == manifest["id"] and info["version"] == manifest["version"] and info["protocol"] == 1
    assert (ROOT / manifest["icon"]).is_file(), "Original icon is required"
    if manifest["slug"]=="color-picker" and args.target=="aarch64-apple-darwin":
        assert (ROOT / "resources/sampler/color-picker-helper").is_file(), "Build the package sampler before packaging"
    executable = "bin/" + TARGETS[args.target]
    files = {executable: args.binary.read_bytes()}
    for name in ["LICENSE", "NOTICE", "README.md", "SOURCE.json"]:
        files[name] = (ROOT / name).read_bytes()
    required = ['resources/icon.png', 'resources/rgb-color-wheel.png', 'resources/tray.png', 'resources/sampler/windows.ps1', 'resources/sampler/windows-modules.ps1', 'resources/sampler/main.swift', 'resources/sampler/build.sh']
    executables = {executable}
    if args.target == "aarch64-apple-darwin":
        helper = "resources/sampler/color-picker-helper"
        required.append(helper)
        executables.add(helper)
        data = (ROOT / helper).read_bytes()
        validate_sampler(data)
    required.extend(path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "licenses").rglob("*")) if path.is_file())
    for name in sorted(required):
        path = ROOT / name
        assert path.is_file() and not path.is_symlink(), f"Missing/unsafe package resource: {name}"
        files[name] = path.read_bytes()
    manifest["files"] = {name: sha(data) for name, data in sorted(files.items())}
    # Archive SHA cannot be included inside itself. Full artifact metadata is
    # external and trusted/pinned by host catalog; source/archive artifacts stay {}.
    files["extension.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / f"color-picker-{args.target}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = ((stat.S_IFREG | (0o755 if name in executables else 0o644)) << 16)
            entry.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(entry, data)
    artifact = {"url": f"{manifest['repository']}/releases/download/v{manifest['version']}/{archive.name}",
                "sha256": sha(archive.read_bytes()), "executable": executable,
                "executableSha256": manifest["files"][executable]}
    fragment = {"id": manifest["id"], "version": manifest["version"], "artifacts": {args.target: artifact}}
    metadata = args.output / f"color-picker-{args.target}.artifact.json"
    metadata.write_text(json.dumps(fragment, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(archive) as package:
        assert set(package.namelist()) == set(files)
        for name, digest in manifest["files"].items():
            assert sha(package.read(name)) == digest
    print(json.dumps({"archive": str(archive), "artifact": str(metadata), "sha256": artifact["sha256"]}))


if __name__ == "__main__":
    main()
