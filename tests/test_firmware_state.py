"""Exercise production C playback with simulated radio, NVS and time boundaries."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FirmwareStateTests(unittest.TestCase):
    def test_production_player_liveness_and_external_off(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "A C compiler is required for firmware state tests")
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "player-state")
            build = subprocess.run(
                [
                    compiler,
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-ffunction-sections",
                    "-fdata-sections",
                    "-I",
                    str(ROOT / "tests/firmware_stubs"),
                    str(ROOT / "tests/player_state.c"),
                    str(ROOT / "firmware-source/main/wire.c"),
                    "-Wl,--gc-sections",
                    "-lm",
                    "-o",
                    binary,
                ],
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([binary], text=True, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 4, run.stdout)
