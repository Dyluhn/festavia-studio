"""Exercise installation boundaries and recovery without erasing a real controller."""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hue-direct"))
spec = importlib.util.spec_from_file_location("direct_wizard", ROOT / "hue-direct/setup.py")
wizard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wizard)


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "private setup"
        self.credentials = self.root / "device.json"
        self.credentials.write_text(json.dumps({"url": "https://192.168.1.20"}))
        self.bridge_file = self.root / "bridge.json"
        self.bridge_file.write_text(
            json.dumps(
                {"bridge": {"host": "192.168.1.10", "pin": "b" * 64, "key": "secret-bridge-key"}}
            )
        )
        self.fixture = {
            "id": "fixture",
            "name": "Front roof",
            "model": "LCX030",
            "software": "1.163.5",
            "reachable": True,
        }
        self.bridge = Mock(config={"address": "192.168.1.10"})
        self.bridge.inventory.return_value = {"lights": [self.fixture], "active_entertainment": []}
        self.status = {
            "ok": True,
            "master": False,
            "owns_player": False,
            "player": {"armed": False},
            "positions": 27,
            "bridge_connected": True,
            "installation_cap": 13,
            "effect": "snake",
            "state": "idle",
            "error": "none",
        }
        self.output = io.StringIO()
        redirect = contextlib.redirect_stdout(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def args(self, mode="resume", *extra):
        args = ["--mode", mode, "--data-dir", str(self.data)]
        if mode != "new":
            args += ["--device-credentials", str(self.credentials)]
        return args + list(extra)

    def commissioning(self, argv):
        result = {
            "positions": 27,
            "controls": {str(n): {"v2": str(n)} for n in range(11, 19)},
            "zone": "zone",
            "scene": "scene",
        }
        Path(argv[argv.index("--output") + 1]).write_text(json.dumps(result))

    def provision(self, argv):
        path = Path(argv[argv.index("--credentials") + 1])
        path.write_text(json.dumps({"url": "https://192.168.1.20"}))

    def test_wireless_resume_reuses_record_preserves_cap_and_never_opens_usb(self):
        with (
            patch.object(wizard, "get_bridge", return_value=(self.bridge, self.bridge_file)),
            patch.object(wizard, "read_status", return_value=({}, self.status)),
            patch.object(wizard, "Link") as serial,
            patch.object(wizard.install, "flash_factory") as flash,
            patch.object(wizard.commission, "main", side_effect=self.commissioning) as commission,
        ):
            wizard.main(self.args())
            wizard.main(self.args())
        serial.assert_not_called()
        flash.assert_not_called()
        self.assertEqual(len(list((self.data / "controllers").iterdir())), 1)
        for call in commission.call_args_list:
            argv = call.args[0]
            self.assertEqual(argv[argv.index("--cap") + 1], "13")
        state = wizard.sessions(self.data)[0][1]
        self.assertEqual(state["phase"], "complete")
        self.assertNotIn("secret-bridge-key", self.output.getvalue())
        if os.name != "nt":
            self.assertEqual(wizard.sessions(self.data)[0][0].stat().st_mode & 0o777, 0o600)

    def test_new_install_and_cancelled_preflight_require_explicit_flash_confirmation(self):
        with (
            patch.object(wizard, "get_bridge", return_value=(self.bridge, self.bridge_file)),
            patch.object(wizard, "select_port", return_value="COM7"),
            patch.object(wizard, "read_status", return_value=({}, self.status)),
            patch.object(wizard.install, "factory_image"),
            patch.object(wizard.install, "flash_factory") as flash,
            patch.object(wizard.install, "provision", side_effect=self.provision),
            patch.object(wizard.commission, "main", side_effect=self.commissioning) as commission,
            patch("builtins.input", side_effect=["cancel", "INSTALL"]),
        ):
            wizard.main(self.args("new", "--ssid", "Home 2.4"))
            flash.assert_not_called()
            state = wizard.sessions(self.data)[0][1]
            self.assertEqual(state["phase"], "prepared")
            # Continue the exact saved session, rather than creating another
            # controller or silently deciding that an earlier flash succeeded.
            wizard.main(["--mode", "resume", "--data-dir", str(self.data)])
        flash.assert_called_once()
        self.assertEqual(wizard.sessions(self.data)[0][1]["phase"], "complete")
        argv = commission.call_args.args[0]
        self.assertEqual(argv[argv.index("--cap") + 1], "19")

    def test_unsupported_fixture_stops_before_flash(self):
        self.bridge.inventory.return_value["lights"][0]["software"] = "different"
        with (
            patch.object(wizard, "get_bridge", return_value=(self.bridge, self.bridge_file)),
            patch.object(wizard, "select_port", return_value="COM7"),
            patch.object(wizard.install, "factory_image"),
            patch.object(wizard.install, "flash_factory") as flash,
            self.assertRaisesRegex(RuntimeError, "No matching supported"),
        ):
            wizard.main(self.args("new", "--ssid", "Home"))
        flash.assert_not_called()

    def test_multiple_fixtures_require_named_selection_and_missing_saved_target_is_not_replaced(
        self,
    ):
        second = dict(self.fixture, id="second", name="Back patio")
        self.bridge.inventory.return_value["lights"].append(second)
        with patch("builtins.input", side_effect=["", "bad", "2"]):
            self.assertEqual(wizard.select_fixture(self.bridge)["id"], "second")
        self.assertIn("Front roof", self.output.getvalue())
        self.assertIn("Back patio", self.output.getvalue())
        with self.assertRaisesRegex(RuntimeError, "No matching supported"):
            wizard.select_fixture(self.bridge, "removed-fixture")

    def test_interrupted_flash_only_probes_firmware_and_never_repeats_the_write(self):
        state = {
            "phase": "flash_started",
            "credentials": str(self.root / "not-yet-created.json"),
            "port": "COM7",
        }
        with (
            patch.object(wizard, "select_port", return_value="COM7"),
            patch.object(wizard, "Link") as serial,
            patch.object(wizard.install, "flash_factory") as flash,
            patch.object(wizard.install, "provision") as provision,
        ):
            serial.return_value.request.side_effect = TimeoutError("firmware did not answer")
            with self.assertRaises(TimeoutError):
                wizard.finish_wifi(
                    SimpleNamespace(port=None, ssid=None), self.root / "setup.json", state
                )
            serial.return_value.close.assert_called_once()
        flash.assert_not_called()
        provision.assert_not_called()

    def test_incomplete_wifi_can_be_finished_without_flashing(self):
        state = {
            "phase": "flashed",
            "credentials": str(self.credentials),
            "port": "COM7",
            "ssid": "Home",
        }
        self.credentials.write_text(json.dumps({"url": None}))
        with (
            patch.object(wizard, "select_port", return_value="COM7"),
            patch.object(wizard.install, "flash_factory") as flash,
            patch.object(wizard.install, "provision", side_effect=self.provision),
            patch("builtins.input", return_value=""),
        ):
            wizard.finish_wifi(
                SimpleNamespace(port=None, ssid=None), self.root / "setup.json", state
            )
        flash.assert_not_called()
        self.assertEqual(state["phase"], "wifi_ready")
        self.assertEqual(json.loads(self.credentials.read_text())["url"], "https://192.168.1.20")

    def test_read_only_status_creates_no_setup_record_or_bridge_authorization(self):
        with (
            patch.object(wizard, "read_status", return_value=({}, self.status)),
            patch.object(wizard, "get_bridge") as bridge,
            patch.object(wizard, "save_state") as save,
            patch.object(wizard, "Link") as serial,
        ):
            wizard.main(self.args("status"))
        self.assertFalse(self.data.exists())
        save.assert_not_called()
        bridge.assert_not_called()
        serial.assert_not_called()
        self.assertIn("Pucks detected: 27", self.output.getvalue())

    def test_already_current_wireless_update_is_skipped_and_new_image_uses_verified_updater(self):
        release = self.root / "release"
        release.mkdir()
        (release / "manifest.json").write_text(json.dumps({"elf_sha256": "current"}))
        args = SimpleNamespace(release=release)
        identity = {"network": {"elf_sha256": "current", "pending_verify": False}}
        with (
            patch.object(wizard, "read_status", return_value=(identity, self.status)),
            patch.object(wizard.update, "main") as updater,
            patch.object(wizard, "Link") as serial,
        ):
            wizard.wireless_update(args, self.credentials)
            updater.assert_not_called()
            identity["network"]["elf_sha256"] = "old"
            wizard.wireless_update(args, self.credentials)
            updater.assert_called_once_with(
                [
                    "--device-credentials",
                    str(self.credentials),
                    "--release",
                    str(release),
                ]
            )
        serial.assert_not_called()

    def test_saved_bridge_does_not_pair_again_and_discovery_fallback_is_manual(self):
        args = SimpleNamespace(existing_bridge=None, bridge=None)
        with patch.object(wizard.commission, "pair") as pair:
            bridge, path = wizard.get_bridge(
                args, {"bridge_file": str(self.bridge_file)}, self.root
            )
            self.assertEqual(path, self.bridge_file)
            self.assertEqual(bridge.config["address"], "192.168.1.10")
            pair.assert_not_called()
        probe = {"address": "192.168.1.10"}
        paired = SimpleNamespace(
            config={"address": "192.168.1.10", "pin": "b" * 64, "key": "private"}
        )
        with (
            patch.object(wizard, "discover_bridges", return_value=[]),
            patch.object(wizard.bridge_lib, "probe", return_value=probe),
            patch.object(wizard.commission, "pair", return_value=paired) as pair,
            patch("builtins.input", return_value="192.168.1.10"),
        ):
            wizard.get_bridge(args, {}, self.root)
            pair.assert_called_once_with("192.168.1.10")

    def test_occupied_controller_is_not_reconfigured(self):
        self.status["owns_player"] = True
        with (
            patch.object(wizard, "get_bridge", return_value=(self.bridge, self.bridge_file)),
            patch.object(wizard, "read_status", return_value=({}, self.status)),
            patch.object(wizard.commission, "main") as commission,
            self.assertRaisesRegex(RuntimeError, "Master off"),
        ):
            wizard.main(self.args())
        commission.assert_not_called()

    def test_new_setup_cannot_overwrite_an_existing_credentials_file(self):
        original = self.credentials.read_bytes()
        with (
            patch.object(wizard.install, "flash_factory") as flash,
            self.assertRaisesRegex(ValueError, "Use Continue"),
        ):
            wizard.main(self.args("new", "--device-credentials", str(self.credentials)))
        flash.assert_not_called()
        self.assertEqual(self.credentials.read_bytes(), original)

    def test_dry_run_does_not_open_devices_pair_or_create_state(self):
        with (
            patch.object(wizard.install, "factory_image"),
            patch.object(wizard.update, "main") as updater,
            patch.object(wizard, "get_bridge") as bridge,
            patch.object(wizard, "Link") as serial,
        ):
            wizard.main(["--data-dir", str(self.data), "--dry-run"])
        self.assertFalse(self.data.exists())
        bridge.assert_not_called()
        serial.assert_not_called()
        self.assertIn("--dry-run", updater.call_args.args[0])

    def test_mdns_discovery_uses_verified_ipv4_bridge_probes(self):
        class Zeroconf:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get_service_info(self, *args, **kwargs):
                return SimpleNamespace(parsed_addresses=lambda: ["192.168.1.10", "fd00::1"])

        browser = Mock()

        def browse(zc, kind, *, handlers):
            self.assertEqual(kind, "_hue._tcp.local.")
            handlers[0](
                zeroconf=zc, service_type=kind, name="Hue._hue._tcp.local.", state_change="added"
            )
            return browser

        library = SimpleNamespace(
            Zeroconf=Zeroconf,
            ServiceBrowser=browse,
            ServiceStateChange=SimpleNamespace(Added="added"),
        )
        with (
            patch.dict(sys.modules, {"zeroconf": library}),
            patch.object(wizard.time, "sleep"),
            patch.object(
                wizard.bridge_lib, "probe", return_value={"address": "192.168.1.10"}
            ) as probe,
        ):
            self.assertEqual(wizard.discover_bridges(), [{"address": "192.168.1.10"}])
        probe.assert_called_once_with("192.168.1.10")
        browser.cancel.assert_called_once()

    def test_port_discovery_excludes_native_usb_and_non_usb_devices(self):
        ports = [
            SimpleNamespace(device="COM1", vid=None),
            SimpleNamespace(device="COM4", vid=0x303A),
            SimpleNamespace(device="COM7", vid=0x10C4, description="CP210x UART"),
        ]
        module = SimpleNamespace(comports=lambda: ports)
        with patch.dict(
            sys.modules,
            {
                "serial": SimpleNamespace(),
                "serial.tools": SimpleNamespace(),
                "serial.tools.list_ports": module,
            },
        ):
            self.assertEqual(wizard.select_port(), "COM7")
            with self.assertRaisesRegex(ValueError, "USB-to-UART"):
                wizard.select_port("COM4")


class BootstrapTests(unittest.TestCase):
    def test_dependencies_are_prepared_once_and_wizard_exit_code_is_forwarded(self):
        bootstrap = wizard.bootstrap
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "requirements.txt").write_text("pyserial>=3.5,<4\n")
            state = root / "private state"

            def create(path):
                python = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                python.parent.mkdir(parents=True)
                python.touch()

            def run(argv, *, check):
                return SimpleNamespace(returncode=0 if check else 17)

            with (
                patch.object(bootstrap, "ROOT", root),
                patch.object(bootstrap.venv, "EnvBuilder") as builder,
                patch.object(bootstrap.subprocess, "run", side_effect=run) as process,
            ):
                builder.return_value.create.side_effect = create
                argv = ["--data-dir", str(state), "--mode", "status"]
                self.assertEqual(bootstrap.main(argv), 17)
                self.assertEqual(bootstrap.main(argv), 17)
                builder.return_value.create.assert_called_once()
                pip_calls = [call for call in process.call_args_list if "pip" in call.args[0]]
                self.assertEqual(len(pip_calls), 1)
                self.assertEqual(process.call_args.args[0][-len(argv) :], argv)

    def test_failed_dependency_install_does_not_mark_the_environment_ready(self):
        bootstrap = wizard.bootstrap
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "requirements.txt").write_text("pyserial>=3.5,<4\n")
            state = root / "private state"
            with (
                patch.object(bootstrap, "ROOT", root),
                patch.object(bootstrap.venv, "EnvBuilder"),
                patch.object(bootstrap.subprocess, "run", side_effect=OSError("offline")),
                self.assertRaises(OSError),
            ):
                bootstrap.main(["--data-dir", str(state)])
            self.assertFalse(list(state.rglob("requirements.sha256")))

    def test_help_does_not_create_an_environment_or_install_dependencies(self):
        bootstrap = wizard.bootstrap
        with (
            patch.object(bootstrap.venv, "EnvBuilder") as builder,
            patch.object(
                bootstrap.subprocess, "run", return_value=SimpleNamespace(returncode=0)
            ) as process,
        ):
            self.assertEqual(bootstrap.main(["--help"]), 0)
        builder.assert_not_called()
        self.assertNotIn("pip", process.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
