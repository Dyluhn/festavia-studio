#!/usr/bin/env python3
"""Package the standalone edition using an explicit public-file allowlist."""

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.5.0"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_files():
    firmware = ROOT / "hue-direct/firmware-source"
    files = [
        firmware / "CMakeLists.txt",
        firmware / "stamp_build.py",
        firmware / "dependencies.lock",
        *sorted((firmware / "main").glob("*")),
        *sorted(firmware.glob("sdkconfig.defaults*")),
        firmware / "partitions.csv",
    ]
    files = [f for f in files if f.is_file()]
    if any(f.is_symlink() for f in files):
        raise ValueError("Symlink in firmware source")
    return files


def check_build(build):
    sys.path.insert(0, str(ROOT / "tools"))
    from transport import module

    data = (build / "hue_mesh_lab.bin").read_bytes()
    info = module("ota").app_info(data)
    description = json.loads((build / "project_description.json").read_text())
    if (
        info["version"] != VERSION
        or description["target"] != "esp32c6"
        or Path(description["project_path"]).resolve()
        != (ROOT / "hue-direct/firmware-source").resolve()
    ):
        raise ValueError("Build is not this standalone source/version/target")
    files = source_files()
    current = {str(f.relative_to(ROOT)): sha(f.read_bytes()) for f in files}
    built = {
        "hue-direct/firmware-source/" + name: digest
        for name, digest in json.loads((build / "hue-direct-source.json").read_text()).items()
    }
    stamp = json.loads((build / "hue-direct-build.json").read_text())
    if stamp["app_sha256"] != info["sha256"] or stamp["sdkconfig_sha256"] != sha(
        Path(description["config_file"]).read_bytes()
    ):
        raise ValueError("Image/configuration no longer matches the successful build record")
    if current != built or stamp["source_sha256"] != json.loads(
        (build / "hue-direct-source.json").read_text()
    ):
        raise ValueError(
            "Firmware source changed since this image was configured; rebuild before packaging"
        )
    return data, description, files, current


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--esptool-python", default=sys.executable)
    args = p.parse_args()
    data, description, files, source_hashes = check_build(args.build)
    release = args.output.parent / ("festavia-direct-" + VERSION + "-images")
    release.mkdir(parents=True, exist_ok=True)
    app = release / "festavia-direct-esp32c6.app.bin"
    app.write_bytes(data)
    factory = release / "festavia-direct-esp32c6.factory.bin"
    flash = json.loads((args.build / "flasher_args.json").read_text())
    command = [
        args.esptool_python,
        "-m",
        "esptool",
        "--chip",
        "esp32c6",
        "merge_bin",
        "-o",
        str(factory),
        "--flash_mode",
        "dio",
        "--flash_size",
        "4MB",
        "--flash_freq",
        "80m",
        "--fill-flash-size",
        "4MB",
    ]
    for offset, path in flash["flash_files"].items():
        command += [offset, str(args.build / path)]
    subprocess.run(command, check=True)
    manifest = {
        "edition": "Festavia Direct",
        "version": VERSION,
        "chip": "esp32c6",
        "flash_size": "4MB",
        "elf_sha256": data[176:208].hex(),
        "esp_idf": data[144:176].split(b"\0", 1)[0].decode("ascii"),
        "sdkconfig_sha256": sha(Path(description["config_file"]).read_bytes()),
        "app": app.name,
        "factory": factory.name,
        "sha256": {f.name: sha(f.read_bytes()) for f in (app, factory)},
        "source_sha256": source_hashes,
        "qualification": {
            "physical": "LCX030 / 1.163.5, 27 pucks, Hue Bridge Pro BSB003",
            "model_test_counts": "1-48",
            "square_bridge": "not physically qualified",
        },
    }
    manifest_path = release / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    entries = {str(f.relative_to(ROOT)): f.read_bytes() for f in files}
    public_files = [
        "hue-direct/README.md",
        "hue-direct/THIRD_PARTY.md",
        "hue-direct/VALIDATION.md",
        "hue-direct/commission.py",
        "hue-direct/hue.py",
        "hue-direct/install.py",
        "hue-direct/update.py",
        "hue-direct/package.py",
        "tools/transport.py",
        "tools/usb_link.py",
        "tools/wifi_setup.py",
    ]
    for relative in public_files:
        entries[relative] = (ROOT / relative).read_bytes()
    entries["README.md"] = (
        b"# Festavia Direct 0.5.0\n\n"
        b"Start with [the installation and Hue control guide](hue-direct/README.md).\n\n"
        b"This is the standalone ESP32-C6 + Hue edition. Home Assistant is not required.\n"
        b"Qualification and current limits are in [VALIDATION.md](hue-direct/VALIDATION.md).\n"
    )
    # Ship only the pure device-library dependency closure. The standalone
    # archive has no custom_components tree or Home Assistant service/server.
    library = ROOT / "hue-direct/device_lib"
    if not library.is_dir():
        library = ROOT / "custom_components/festavia_studio/backend/lib"
    pending = {"bridge", "control", "net_client", "ota"}
    included = set()
    while pending:
        name = pending.pop()
        if name in included:
            continue
        included.add(name)
        f = library / (name + ".py")
        raw = f.read_bytes()
        entries["hue-direct/device_lib/" + f.name] = raw
        for node in ast.walk(ast.parse(raw)):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                pending.add(node.module.split(".")[0])
    entries["hue-direct/device_lib/__init__.py"] = (library / "__init__.py").read_bytes()
    entries["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    # Carry SDK/library notices with downloadable images, including the
    # separately licensed ZBOSS binary. Only license files enter the archive.
    idf = Path(description["idf_path"])
    for base, label in [
        (idf, "esp-idf"),
        *[
            (Path(p), "components/" + Path(p).name)
            for p in description["build_component_paths"]
            if p
        ],
    ]:
        candidates = [base / "LICENSE", base / "NOTICE", base / "COPYING"]
        if label != "esp-idf":
            candidates += [
                p
                for p in base.rglob("*")
                if p.is_file() and p.name.upper().startswith(("LICENSE", "NOTICE", "COPYING"))
            ]
        for f in candidates:
            if f.is_file():
                entries["hue-direct/licenses/" + label + "/" + str(f.relative_to(base))] = (
                    f.read_bytes()
                )
    entries["requirements.txt"] = b"pyserial>=3.5,<4\nesptool>=4.8,<5\n"
    for f in (app, factory, manifest_path):
        entries["hue-direct/release/" + f.name] = f.read_bytes()
    entries["SHA256SUMS"] = "".join(
        f"{sha(raw)}  {name}\n" for name, raw in sorted(entries.items())
    ).encode()
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(entries.items()):
            info = zipfile.ZipInfo(
                "festavia-direct-" + VERSION + "/" + name, date_time=(2026, 11, 9, 0, 0, 0)
            )
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    with zipfile.ZipFile(args.output) as z:
        assert z.testzip() is None
    args.output.with_suffix(".zip.sha256").write_text(
        sha(args.output.read_bytes()) + "  " + args.output.name + "\n"
    )
    print(str(args.output))


if __name__ == "__main__":
    main()
