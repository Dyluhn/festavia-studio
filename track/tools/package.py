#!/usr/bin/env python3
"""Make a redistributable source/print kit from explicit public inputs only."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import trackkit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--example-kit", type=Path, action="append", default=[])
    args = parser.parse_args()
    entries = {}
    root = trackkit.ROOT
    for name in [
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "LISTING.md",
        "CHANGELOG.md",
        "festavia_track.scad",
        "festavia_track.json",
        "make_track.py",
        "workbench/index.html",
        "workbench/README.md",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-docs.txt",
        "Make Track Windows.cmd",
        "Make Track macOS.command",
        "Make Track Linux.sh",
        ".gitignore",
        ".gitattributes",
    ]:
        path = root / name
        if path.is_symlink():
            raise ValueError("symlink in public source")
        entries[name] = path.read_bytes()
    for folder, suffixes in [
        ("tools", {".py"}),
        ("tests", {".py"}),
        ("examples", {".json", ".3mf"}),
        ("makerworld", {".py", ".scad", ".in", ".md", ".jpg"}),
        ("docs", {".md", ".json", ".pdf", ".html", ".css"}),
        ("accessories", {".stl", ".md"}),
        ("assets", {".png", ".svg", ".jpg"}),
    ]:
        for path in sorted((root / folder).rglob("*")):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            if path.is_symlink() or path.suffix not in suffixes:
                raise ValueError(
                    "unexpected public source: " + str(path.relative_to(root))
                )
            entries[path.relative_to(root).as_posix()] = path.read_bytes()
    for kit in args.example_kit:
        trackkit.verify(kit)
        manifest = json.loads((kit / "manifest.json").read_text())
        if manifest["model_sha256"] != trackkit.digest(trackkit.MODEL.read_bytes()):
            raise ValueError("example kit uses a different source model")
        name = manifest["config"]["name"]
        # Include only files attested by the completed exporter, not unrelated
        # files someone might put beside a kit or in a private setup directory.
        for relative in [*manifest["files"], "manifest.json", "SHA256SUMS"]:
            path = (kit / relative).resolve()
            if not path.is_relative_to(kit.resolve()):
                raise ValueError("unsafe kit path")
            entries["printable-examples/" + name + "/" + relative] = path.read_bytes()
    entries["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(raw).hexdigest()}  {name}\n"
        for name, raw in sorted(entries.items())
    ).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("output ZIP already exists")
    prefix = "festavia-track-" + trackkit.VERSION + "/"
    with zipfile.ZipFile(
        args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, raw in sorted(entries.items()):
            info = zipfile.ZipInfo(prefix + name, (2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (
                0o100755 if name.endswith((".sh", ".command")) else 0o100644
            ) << 16
            archive.writestr(info, raw)
    with zipfile.ZipFile(args.output) as z:
        assert z.testzip() is None
        for line in z.read(prefix + "SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(z.read(prefix + name)).hexdigest() == digest
    print(
        json.dumps(
            {
                "archive": str(args.output),
                "files": len(entries),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "bytes": args.output.stat().st_size,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
