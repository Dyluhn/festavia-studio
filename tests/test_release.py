"""Build real release archives and refuse secrets or unverified firmware."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        shutil.copytree(
            ROOT,
            self.root,
            ignore=shutil.ignore_patterns(".venv", ".git", "__pycache__", "test-results", "*.pyc"),
        )
        self.output = Path(self.temp.name) / "release.zip"

    def run_package(self):
        return subprocess.run(
            [sys.executable, str(self.root / "tools/package.py"), "--output", str(self.output)],
            capture_output=True,
            text=True,
        )

    def test_clean_release_is_native_and_checksum_verified(self):
        result = self.run_package()
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertTrue(info["firmware_verified"] and info["source_verified"])
        with zipfile.ZipFile(info["integration_archive"]) as archive:
            names = archive.namelist()
            self.assertIn("custom_components/festavia_studio/config_flow.py", names)
            self.assertFalse(
                any(
                    "/web/" in n or n.endswith("config.yaml") or "hue_mesh_studio" in n
                    for n in names
                )
            )

    def test_private_runtime_files_and_symlinks_abort_packaging(self):
        folder = self.root / "custom_components/festavia_studio"
        for name in (
            "credentials.json",
            "player-session.json",
            "studio-presets.json",
            "removal-pending.json",
            "unload-pending.json",
        ):
            with self.subTest(name=name):
                path = folder / name
                path.write_text('{"secret":"private-release-test"}')
                result = self.run_package()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
                path.unlink()
        link = folder / "linked-data"
        link.symlink_to(self.root / "firmware-release", target_is_directory=True)
        self.assertNotEqual(self.run_package().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_modified_firmware_cannot_be_released(self):
        app = self.root / "firmware-release/esp32c6/hue-mesh-lab.app.bin"
        app.write_bytes(app.read_bytes() + b"corrupt")
        self.assertNotEqual(self.run_package().returncode, 0)
        self.assertFalse(self.output.exists())
