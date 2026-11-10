"""Exercise onboarding interruption boundaries; never open USB or contact a device."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ha_setup as wizard
import bootstrap

DEVICE = {
    "target": "esp32c6",
    "url": "https://192.168.1.3",
    "token": "a" * 64,
    "tls_sha256": "b" * 64,
}


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private data"
        self.output = Path(self.temp.name) / "download/festavia-ha-connection.json"
        self.stdout = io.StringIO()
        self.enter(contextlib.redirect_stdout(self.stdout))
        self.flash = self.enter(patch.object(wizard.installer, "flash_factory"))
        self.provision = self.enter(
            patch.object(wizard.installer, "provision", side_effect=self.wifi)
        )
        self.select_port = wizard.select_port
        self.port = self.enter(patch.object(wizard, "select_port", return_value="COM7"))
        self.read = self.enter(
            patch.object(wizard, "read_status", return_value=(DEVICE, {"version": "0.4.0"}))
        )
        self.link = self.enter(
            patch.object(wizard, "Link", side_effect=AssertionError("unexpected USB"))
        )

    def enter(self, cm):
        value = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return value

    @staticmethod
    def wifi(argv):
        path = Path(argv[argv.index("--credentials") + 1])
        wizard.net.save_credentials(path, DEVICE)

    def run_wizard(self, mode, *extra, answers=()):
        with patch("builtins.input", side_effect=answers):
            return wizard.main(
                ["--mode", mode, "--data-dir", str(self.root), "--output", str(self.output), *extra]
            )

    def new(self):
        self.run_wizard("new", "--ssid", "Test Wi-Fi", answers=["INSTALL"])
        return wizard.sessions(self.root)[0]

    def test_first_install_exports_private_file_and_retains_progress_without_password(self):
        path, state = self.new()
        self.flash.assert_called_once_with("COM7")
        self.assertEqual(state["phase"], "complete")
        exported = self.output
        value = json.loads(exported.read_text())
        self.assertEqual(value["device"], DEVICE)
        self.assertEqual(value["edition"], "home_assistant")
        self.assertNotIn(DEVICE["token"], self.stdout.getvalue())
        self.assertNotIn("password", path.read_text().lower())
        if os.name != "nt":
            self.assertEqual(exported.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cancel_never_writes_board_or_setup(self):
        self.run_wizard("new", "--ssid", "Test", answers=["cancel"])
        self.flash.assert_not_called()
        self.provision.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_bad_image_refuses_before_port_selection(self):
        with patch.object(wizard.installer, "factory_image", side_effect=ValueError("checksum")):
            with self.assertRaises(ValueError):
                self.run_wizard("new", "--ssid", "Test")
        self.port.assert_not_called()
        self.flash.assert_not_called()

    def test_ready_resume_export_and_check_never_open_usb_or_provision(self):
        path, state = self.new()
        self.flash.reset_mock()
        self.port.reset_mock()
        self.provision.reset_mock()
        before = Path(state["credentials"]).read_bytes()
        for mode in ("resume", "export", "status"):
            self.run_wizard(mode)
        self.flash.assert_not_called()
        self.provision.assert_not_called()
        self.port.assert_not_called()
        self.link.assert_not_called()
        self.assertEqual(Path(state["credentials"]).read_bytes(), before)
        self.assertEqual(len(wizard.sessions(self.root)), 1)

    def test_wifi_failure_resumes_without_reflashing(self):
        def fail(argv):
            wizard.net.save_credentials(Path(argv[-1]), dict(DEVICE, url=None))
            raise TimeoutError("Wi-Fi timeout")

        self.provision.side_effect = fail
        with self.assertRaises(TimeoutError):
            self.run_wizard("new", "--ssid", "Test", answers=["INSTALL"])
        self.provision.side_effect = self.wifi
        self.run_wizard("resume", answers=[""])
        self.assertEqual(self.flash.call_count, 1)
        self.assertEqual(wizard.sessions(self.root)[0][1]["phase"], "complete")

    def test_interrupted_flash_probes_expected_image_without_writing_again(self):
        self.flash.side_effect = subprocess.CalledProcessError(1, ["esptool"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_wizard("new", "--ssid", "Test", answers=["INSTALL"])
        self.assertEqual(wizard.sessions(self.root)[0][1]["phase"], "flash_started")
        with patch.object(wizard, "probe_interrupted_flash") as probe:
            self.run_wizard("resume", answers=[""])
        probe.assert_called_once_with("COM7")
        self.assertEqual(self.flash.call_count, 1)

    def test_unverified_interrupted_image_never_provisions(self):
        self.flash.side_effect = OSError("disconnected")
        with self.assertRaises(OSError):
            self.run_wizard("new", "--ssid", "Test", answers=["INSTALL"])
        with patch.object(wizard, "probe_interrupted_flash", side_effect=ValueError("wrong image")):
            with self.assertRaises(ValueError):
                self.run_wizard("resume")
        self.provision.assert_not_called()
        self.assertEqual(self.flash.call_count, 1)

    def test_https_failure_retains_wifi_credentials_and_retry_does_not_use_usb(self):
        self.read.side_effect = OSError("HTTPS unavailable")
        with self.assertRaises(OSError):
            self.run_wizard("new", "--ssid", "Test", answers=["INSTALL"])
        self.assertEqual(wizard.sessions(self.root)[0][1]["phase"], "wifi_ready")
        self.read.side_effect = None
        self.run_wizard("resume")
        self.assertEqual(self.flash.call_count, 1)
        self.assertEqual(self.provision.call_count, 1)

    def test_export_existing_credentials_creates_no_duplicate_setup(self):
        source = Path(self.temp.name) / "old-device.json"
        wizard.net.save_credentials(source, DEVICE)
        output = Path(self.temp.name) / "handoff.json"
        self.run_wizard("export", "--credentials", str(source), "--output", str(output))
        self.assertTrue(output.exists())
        self.assertFalse(self.root.exists())
        self.flash.assert_not_called()
        self.port.assert_not_called()

    def test_export_cannot_overwrite_its_source_or_setup_record(self):
        source = Path(self.temp.name) / "old-device.json"
        wizard.net.save_credentials(source, DEVICE)
        for output in (source, source.with_name("setup.json")):
            with self.assertRaises(ValueError):
                wizard.export_connection(source, output)
        self.assertEqual(json.loads(source.read_text()), DEVICE)

    def test_dry_run_needs_no_setup_files_usb_or_network(self):
        wizard.main(["--dry-run", "--data-dir", str(self.root)])
        self.assertFalse(self.root.exists())
        self.read.assert_not_called()
        self.link.assert_not_called()
        self.flash.assert_not_called()

    def test_multiple_controllers_require_a_choice(self):
        rows = [(1, "first"), (2, "second")]
        with patch("builtins.input", side_effect=["invalid", "0", "2"]):
            self.assertEqual(wizard.choose("Controller", rows, lambda r: r[1]), rows[1])

    def test_usb_selection_excludes_native_connector_and_can_choose_among_uart_devices(self):
        ports = [
            SimpleNamespace(device="COM1", vid=0x303A, description="Native USB"),
            SimpleNamespace(device="COM2", vid=0x10C4, description="UART A"),
            SimpleNamespace(device="COM3", vid=0x1A86, description="UART B"),
        ]
        with patch("serial.tools.list_ports.comports", return_value=ports):
            with patch("builtins.input", return_value="2"):
                self.assertEqual(self.select_port(), "COM3")
            with self.assertRaises(ValueError):
                self.select_port("COM1")


class ImageIdentityTests(unittest.TestCase):
    def test_wireless_export_rejects_wrong_image_and_closes_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            credentials = Path(folder) / "private.json"
            wizard.net.save_credentials(credentials, DEVICE)
            with patch.object(wizard.net, "PinnedHTTPS") as api:
                api.return_value.call.return_value = {
                    "firmware": "hue-mesh-lab",
                    "target": "esp32c6",
                    "version": "0.5.0",
                    "network": {"elf_sha256": "0" * 64},
                }
                with self.assertRaises(ValueError):
                    wizard.read_status(credentials)
                api.return_value.close.assert_called_once()

    def test_running_image_binding_accepts_supplied_firmware(self):
        with tempfile.TemporaryDirectory() as folder:
            credentials = Path(folder) / "private.json"
            wizard.net.save_credentials(credentials, DEVICE)
            with patch.object(wizard.net, "PinnedHTTPS") as api:
                api.return_value.call.return_value = {
                    "firmware": "hue-mesh-lab",
                    "target": "esp32c6",
                    "version": "0.4.0",
                    "network": {"elf_sha256": wizard.expected_elf()},
                }
                config, _ = wizard.read_status(credentials)
                self.assertEqual(config, DEVICE)


class BootstrapTests(unittest.TestCase):
    def test_help_skips_all_dependency_preparation(self):
        with (
            patch.object(bootstrap.venv, "EnvBuilder") as venv,
            patch.object(bootstrap.subprocess, "run") as run,
        ):
            run.return_value.returncode = 0
            self.assertEqual(bootstrap.main(["--help"]), 0)
            venv.assert_not_called()
            self.assertIn("ha_setup.py", run.call_args.args[0][1])

    def test_failed_dependency_install_is_retried_and_success_marker_is_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tools = root / f"tools-py{sys.version_info.major}.{sys.version_info.minor}"
            python = tools / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python.parent.mkdir(parents=True)
            python.touch()
            marker = tools / "requirements.sha256"
            args = ["--data-dir", str(root), "--dry-run"]
            with patch.object(
                bootstrap.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["pip"])
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    bootstrap.main(args)
            self.assertFalse(marker.exists())
            with patch.object(bootstrap.subprocess, "run") as run:
                run.return_value.returncode = 0
                bootstrap.main(args)
                self.assertEqual(run.call_count, 2)
                self.assertTrue(marker.exists())
                run.reset_mock()
                bootstrap.main(args)
                self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
