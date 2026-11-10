"""Release images must match successful builds; the ZIP needs no HA install."""

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("direct_package", ROOT / "hue-direct/package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def fixture(self, root):
        build = root / "build"
        build.mkdir()
        image = bytearray(320)
        image[0] = 0xE9
        struct.pack_into("<H", image, 12, 13)
        struct.pack_into("<I", image, 32, 0xABCD5432)
        image[48 : 48 + len(package.VERSION)] = package.VERSION.encode()
        image[80:92] = b"hue_mesh_lab"
        (build / "hue_mesh_lab.bin").write_bytes(image)
        config = build / "sdkconfig"
        config.write_text('CONFIG_IDF_TARGET="esp32c6"\n')
        idf = root / "idf"
        idf.mkdir()
        (idf / "LICENSE").write_text("Test SDK notice\n")
        description = {
            "target": "esp32c6",
            "project_path": str(ROOT / "hue-direct/firmware-source"),
            "config_file": str(config),
            "idf_path": str(idf),
            "build_component_paths": [""],
        }
        (build / "project_description.json").write_text(json.dumps(description))
        source = {
            f.relative_to(ROOT / "hue-direct/firmware-source").as_posix(): package.sha(
                f.read_bytes()
            )
            for f in package.source_files()
        }
        (build / "hue-direct-source.json").write_text(json.dumps(source))
        (build / "hue-direct-build.json").write_text(
            json.dumps(
                {
                    "app_sha256": package.sha(image),
                    "sdkconfig_sha256": package.sha(config.read_bytes()),
                    "source_sha256": source,
                }
            )
        )
        (build / "flasher_args.json").write_text(
            json.dumps({"flash_files": {"0x20000": "hue_mesh_lab.bin"}})
        )
        return build

    def test_source_image_and_configuration_are_bound_to_completed_build(self):
        with tempfile.TemporaryDirectory() as folder:
            build = self.fixture(Path(folder))
            original = (build / "hue_mesh_lab.bin").read_bytes()
            self.assertEqual(package.check_build(build)[0], original)
            altered = bytearray(original)
            altered[250] = 1
            (build / "hue_mesh_lab.bin").write_bytes(altered)
            with self.assertRaisesRegex(ValueError, "successful build"):
                package.check_build(build)
            (build / "hue_mesh_lab.bin").write_bytes(original)
            source = json.loads((build / "hue-direct-source.json").read_text())
            source["CMakeLists.txt"] = "0" * 64
            (build / "hue-direct-source.json").write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, "source changed"):
                package.check_build(build)
            source["CMakeLists.txt"] = package.sha(
                (ROOT / "hue-direct/firmware-source/CMakeLists.txt").read_bytes()
            )
            (build / "hue-direct-source.json").write_text(json.dumps(source))
            (build / "sdkconfig").write_text("unexpected configuration")
            with self.assertRaisesRegex(ValueError, "configuration"):
                package.check_build(build)

    def test_extracted_standalone_archive_has_no_ha_tree_and_imports_all_clis(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            build = self.fixture(root)
            target = root / "release/festavia-direct.zip"
            image_folder = target.parent / f"festavia-direct-{package.VERSION}-images"
            image_folder.mkdir(parents=True)
            (image_folder / "private-unrelated.json").write_text('{"key":"private"}')

            def merge(command, **kwargs):
                self.assertIn("esptool", command)
                Path(command[command.index("-o") + 1]).write_bytes(b"factory fixture")

            with (
                patch.object(
                    sys, "argv", ["package.py", "--build", str(build), "--output", str(target)]
                ),
                patch.object(package.subprocess, "run", side_effect=merge),
            ):
                package.main()
            with zipfile.ZipFile(target) as archive:
                self.assertFalse(any("private-unrelated" in n for n in archive.namelist()))
                self.assertFalse(any("/custom_components/" in n for n in archive.namelist()))
                self.assertFalse(
                    any(n.endswith(("/service.py", "/studio.py")) for n in archive.namelist())
                )
                for name in ("Setup macOS.command", "Setup Linux.sh"):
                    self.assertTrue(
                        archive.getinfo(f"festavia-direct-{package.VERSION}/" + name).external_attr
                        >> 16
                        & 0o111
                    )
                archive.extractall(root / "extract with spaces")
            extracted = next((root / "extract with spaces").iterdir())
            self.assertTrue((extracted / "hue-direct/GETTING_STARTED.md").is_file())
            for line in (extracted / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(
                    hashlib.sha256((extracted / name).read_bytes()).hexdigest(), digest
                )
            for cli in ("commission.py", "install.py", "update.py", "setup.py", "bootstrap.py"):
                result = subprocess.run(
                    [sys.executable, str(extracted / "hue-direct" / cli), "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            launcher = (
                ["cmd", "/c", str(extracted / "Setup Windows.cmd"), "--help"]
                if os.name == "nt"
                else ["sh", str(extracted / "Setup Linux.sh"), "--help"]
            )
            result = subprocess.run(launcher, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)

            # Repackage with the extracted tool, not the developer worktree or SDK.
            repacked = root / "repacked/direct.zip"
            result = subprocess.run(
                [
                    sys.executable,
                    str(extracted / "hue-direct/package.py"),
                    "--reuse-archive",
                    str(target),
                    "--output",
                    str(repacked),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(package.sha(target.read_bytes()), package.sha(repacked.read_bytes()))
            corrupt = root / "corrupt.zip"
            with zipfile.ZipFile(target) as original, zipfile.ZipFile(corrupt, "w") as altered:
                for name in original.namelist():
                    raw = original.read(name)
                    if name.endswith(".app.bin"):
                        raw += b"changed"
                    altered.writestr(name, raw)
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                package.reuse_archive(corrupt, root / "refused/out.zip")
            result = subprocess.run(
                [sys.executable, str(extracted / "hue-direct/setup.py"), "--dry-run"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
