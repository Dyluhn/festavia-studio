#!/usr/bin/env python3
"""Build both editions under one HA-compatible project release version."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--direct-build", type=Path)
    source.add_argument("--direct-archive", type=Path)
    args = parser.parse_args()
    version = json.loads((ROOT / "custom_components/festavia_studio/manifest.json").read_text())[
        "version"
    ]
    if args.tag != "v" + version:
        parser.error("The project release tag must match the HA integration manifest")
    args.output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/package.py"),
            "--output",
            str(args.output / f"festavia-studio-{version}.zip"),
        ],
        check=True,
    )
    # Keep the firmware version independent from the project/integration version.
    # The emitted manifest is authoritative for the unchanged standalone image.
    direct_output = args.output / "direct"
    direct_output.mkdir(exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "hue-direct/package.py"),
            "--build" if args.direct_build else "--reuse-archive",
            str(args.direct_build or args.direct_archive),
            "--output",
            str(direct_output / "package.zip"),
        ],
        check=True,
    )
    image_folder = next(direct_output.glob("festavia-direct-*-images"))
    manifest = json.loads((image_folder / "manifest.json").read_text())
    direct_version = manifest["version"]
    shutil.move(
        direct_output / "package.zip", args.output / f"festavia-direct-{direct_version}.zip"
    )
    for name in (manifest["app"], manifest["factory"]):
        shutil.copyfile(image_folder / name, args.output / name)
    shutil.copyfile(
        image_folder / "manifest.json",
        args.output / f"festavia-direct-{direct_version}-manifest.json",
    )
    shutil.rmtree(direct_output)
    files = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(args.output.iterdir())
        if p.is_file() and p.name not in ("SHA256SUMS", "release-manifest.json")
    }
    release = {
        "tag": args.tag,
        "integration_version": version,
        "ha_firmware_version": json.loads((ROOT / "firmware-release/manifest.json").read_text())[
            "version"
        ],
        "direct_firmware_version": direct_version,
        "sha256": files,
    }
    target = args.output / "release-manifest.json"
    target.write_text(json.dumps(release, indent=2) + "\n")
    files[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (args.output / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(files.items()))
    )


if __name__ == "__main__":
    main()
