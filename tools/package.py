#!/usr/bin/env python3
"""Build private-data-free native integration and community source archives."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/festavia_studio"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_zip(path, entries, prefix=""):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(entries.items()):
            info = zipfile.ZipInfo(prefix + name, date_time=(2026, 11, 8, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None


def main():
    version = json.loads((COMPONENT / "manifest.json").read_text())["version"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT.parent / f"festavia-studio-{version}.zip"
    )
    args = parser.parse_args()
    release = ROOT / "firmware-release"
    manifest = json.loads((release / "manifest.json").read_text())
    for name, digest in manifest["sha256"].items():
        assert sha((release / name).read_bytes()) == digest, name
    for name, digest in manifest["firmware_source_sha256"].items():
        assert (
            sha((ROOT / "firmware-source" / name.removeprefix("firmware/")).read_bytes()) == digest
        ), name
    app = manifest["targets"]["esp32c6"]["app"]
    assert sha((COMPONENT / "backend/release" / app).read_bytes()) == manifest["sha256"][app]
    entries = {}
    excluded = {"__pycache__", ".git", ".venv", "node_modules", "test-results"}
    private = {
        "installation.json",
        "credentials.json",
        "options.json",
        "bridge-session.json",
        "player-session.json",
        "ha-connection.json",
        "studio-presets.json",
        "bridge-presets.json",
        "color-palettes.json",
        "migration-options.json",
        "removal-pending.json",
        "unload-pending.json",
        "auth.json",
    }

    def add(folder, target):
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlink in release source")
            if not path.is_file() or set(path.parts) & excluded or path.suffix in (".pyc", ".zip"):
                continue
            if (
                path.is_symlink()
                or path.name in private
                or (
                    path.name.endswith("-credentials.json")
                    or path.name in ("player-operation.lock",)
                    or path.name.endswith((".owner.lock", ".active.json"))
                )
                or any(
                    part in (".storage", "uniform-commits", ".setup-data") for part in path.parts
                )
            ):
                raise ValueError("Private runtime file in release source")
            entries[str(Path(target) / path.relative_to(folder))] = path.read_bytes()

    for name in (
        "README.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "hacs.json",
        "requirements-usb.txt",
        "requirements-dev.txt",
        ".gitignore",
        "pyproject.toml",
    ):
        entries[name] = (ROOT / name).read_bytes()
    for name in ("custom_components", "firmware-source", "third_party", "tests", ".github"):
        add(ROOT / name, name)
    for name in (
        "HA_DESIGN.md",
        "RESEARCH.md",
        "ACCEPTANCE.md",
        "FIRMWARE.md",
        "FIRMWARE_ACCEPTANCE.json",
    ):
        entries["docs/" + name] = (ROOT / "docs" / name).read_bytes()
    for name in (
        "first-install.py",
        "wifi_setup.py",
        "usb_link.py",
        "transport.py",
        "package.py",
        "check.sh",
    ):
        entries["tools/" + name] = (ROOT / "tools" / name).read_bytes()
    add(release, "firmware-release")
    sums = "".join(f"{sha(raw)}  {name}\n" for name, raw in sorted(entries.items()))
    entries["SHA256SUMS"] = sums.encode()
    write_zip(args.output, entries, "festavia-studio/")
    integration = args.output.parent / f"festavia-studio-integration-{version}.zip"
    native = {
        name: raw
        for name, raw in entries.items()
        if name.startswith("custom_components/") or name in ("README.md", "LICENSE", "hacs.json")
    }
    write_zip(integration, native)
    assert not any("config.yaml" in name or "/web/" in name for name in native)
    print(
        json.dumps(
            {
                "archive": str(args.output),
                "sha256": sha(args.output.read_bytes()),
                "files": len(entries),
                "integration_archive": str(integration),
                "integration_sha256": sha(integration.read_bytes()),
                "firmware_verified": True,
                "source_verified": True,
                "no_installable_addon": True,
            }
        )
    )


if __name__ == "__main__":
    main()
