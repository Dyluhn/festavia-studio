"""Run the actual desktop entry point from a clean, checksum-verified release ZIP."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class SetupPackageTests(unittest.TestCase):
    def test_extracted_setup_launchers_and_clis_work_from_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/package.py"),
                    "--output",
                    str(root / "release.zip"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            with zipfile.ZipFile(report["archive"]) as archive:
                archive.extractall(root / "folder with spaces")
                for name in ("Setup Home Assistant Linux.sh", "Setup Home Assistant macOS.command"):
                    self.assertTrue(
                        archive.getinfo("festavia-studio/" + name).external_attr >> 16 & 0o111
                    )
            source = root / "folder with spaces/festavia-studio"
            for line in (source / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((source / name).read_bytes()).hexdigest(), digest)
            for cli in ("bootstrap.py", "ha_setup.py", "first-install.py"):
                result = subprocess.run(
                    [sys.executable, str(source / "tools" / cli), "--help"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            launcher = (
                ["cmd", "/d", "/c", str(source / "Setup Home Assistant Windows.cmd"), "--help"]
                if os.name == "nt"
                else [
                    "sh",
                    str(
                        source
                        / (
                            "Setup Home Assistant macOS.command"
                            if sys.platform == "darwin"
                            else "Setup Home Assistant Linux.sh"
                        )
                    ),
                    "--help",
                ]
            )
            result = subprocess.run(launcher, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(
                [sys.executable, str(source / "tools/ha_setup.py"), "--dry-run"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(report["integration_archive"]) as archive:
                self.assertIn("docs/INSTALL.md", archive.namelist())
                self.assertIn("custom_components/festavia_studio/connection.py", archive.namelist())
                self.assertFalse(
                    any("launchers" in n or n.startswith("tools/") for n in archive.namelist())
                )
            rebuilt = subprocess.run(
                [
                    sys.executable,
                    str(source / "tools/package.py"),
                    "--output",
                    str(root / "repacked/release.zip"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stdout + rebuilt.stderr)
            rebuilt = json.loads(rebuilt.stdout)
            self.assertEqual(rebuilt["sha256"], report["sha256"])
            self.assertEqual(rebuilt["integration_sha256"], report["integration_sha256"])


if __name__ == "__main__":
    unittest.main()
