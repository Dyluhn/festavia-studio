"""Run the same radio/recovery boundaries against the standalone player's build."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DirectPlayerTests(unittest.TestCase):
    def test_current_transfer_tracking_and_missing_confirmation_expiration(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "direct-transfers")
            subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(ROOT / "tests/direct_transfers.c"),
                    "-o",
                    binary,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            run = subprocess.run([binary], check=False, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 7, run.stdout)

    def test_coordinator_preparation_priority_debounce_and_group_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "direct-state")
            include = Path(
                os.environ.get(
                    "CJSON_SOURCE",
                    str(Path(os.environ.get("IDF_PATH", "/nonexistent")) / "components/json/cJSON"),
                )
            )
            args = [
                "cc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-ffunction-sections",
                "-fdata-sections",
            ]
            if (include / "cJSON.c").exists():
                args += ["-I", str(include), str(include / "cJSON.c")]
            elif Path("/usr/include/cjson/cJSON.h").exists():
                args += ["-I", "/usr/include/cjson"]
            else:
                raise RuntimeError("Install libcjson-dev or set CJSON_SOURCE")
            args += [
                "-I",
                str(ROOT / "tests/direct_stubs"),
                "-I",
                str(ROOT / "tests/firmware_stubs"),
                str(ROOT / "tests/direct_state.c"),
            ]
            args += [
                str(ROOT / "hue-direct/firmware-source/main" / f)
                for f in ("direct_model.c", "direct_program.c", "wire.c")
            ]
            if not (include / "cJSON.c").exists():
                args += ["-lcjson"]
            args += ["-Wl,--gc-sections", "-lm", "-o", binary]
            build = subprocess.run(args, check=False, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([binary], check=False, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 47, run.stdout)

    def test_failed_prepare_cannot_leave_an_unowned_recovery_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "direct-persist")
            include = Path(
                os.environ.get(
                    "CJSON_SOURCE",
                    str(Path(os.environ.get("IDF_PATH", "/nonexistent")) / "components/json/cJSON"),
                )
            )
            args = [
                "cc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-ffunction-sections",
                "-fdata-sections",
            ]
            if (include / "cJSON.c").exists():
                args += ["-I", str(include), str(include / "cJSON.c")]
            elif Path("/usr/include/cjson/cJSON.h").exists():
                args += ["-I", "/usr/include/cjson"]
            else:
                raise RuntimeError("Install libcjson-dev or set CJSON_SOURCE")
            args += ["-I", str(ROOT / "tests/firmware_stubs"), str(ROOT / "tests/direct_persist.c")]
            args += [
                str(ROOT / "hue-direct/firmware-source/main" / f)
                for f in ("direct_model.c", "direct_program.c", "wire.c")
            ]
            if not (include / "cJSON.c").exists():
                args += ["-lcjson"]
            args += ["-Wl,--gc-sections", "-lm", "-o", binary]
            build = subprocess.run(args, check=False, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([binary], check=False, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 5, run.stdout)

    def test_storage_reservation_and_migration_fault_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "direct-storage")
            build = subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-ffunction-sections",
                    "-fdata-sections",
                    "-I",
                    str(ROOT / "tests/storage_stubs"),
                    "-I",
                    str(ROOT / "tests/firmware_stubs"),
                    str(ROOT / "tests/direct_storage.c"),
                    "-Wl,--gc-sections",
                    "-o",
                    binary,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([binary], check=False, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 13, run.stdout)

    def test_standalone_player_passes_shared_liveness_and_handoff_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "player-state.c"
            source.write_text(
                (ROOT / "tests/player_state.c")
                .read_text()
                .replace(
                    '"../firmware-source/main/player.c"',
                    '"' + str(ROOT / "hue-direct/firmware-source/main/player.c") + '"',
                )
            )
            binary = str(Path(directory) / "player-state")
            build = subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-ffunction-sections",
                    "-fdata-sections",
                    "-I",
                    str(ROOT / "tests/firmware_stubs"),
                    str(source),
                    str(ROOT / "hue-direct/firmware-source/main/wire.c"),
                    "-Wl,--gc-sections",
                    "-lm",
                    "-o",
                    binary,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([binary], check=False, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 14, run.stdout)
