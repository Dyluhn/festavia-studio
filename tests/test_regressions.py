"""Regression coverage for the independent review's production-library defects."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from protocol import bridge, errors, net_client, player, service, studio
from test_portable import FakeBridge, light

ROOT = Path(__file__).resolve().parents[1]


class RecoveryTests(unittest.TestCase):
    def test_changing_selection_cannot_reuse_or_erase_an_old_bridge_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            app = service.Installation(folder, brightness_limit=15)
            fake = FakeBridge([light(1, 5), light(2, 5)])
            app.bridge = lambda: fake
            app.data.update(bridge={"id": "test"}, selected=["1"])
            scene = {"colors": ["#ff0000"], "brightness": 10}
            app.control("play", {"scene": scene})
            captured = app.bridge_journal.read_bytes()
            with self.assertRaises(errors.RecoveryPending):
                app.setup("select", {"ids": ["2"], "mode": "bridge"})
            self.assertEqual(app.data["selected"], ["1"])
            # Also protect against stale/corrupted persisted data bypassing setup.
            app.data["selected"] = ["2"]
            with self.assertRaises(errors.RecoveryPending):
                app.control("play", {"scene": scene})
            self.assertEqual(app.bridge_journal.read_bytes(), captured)
            self.assertFalse(fake.lights[1]["state"]["on"]["on"])
            app.bridge_restore()
            self.assertFalse(fake.lights[0]["state"]["on"]["on"])

    def test_bridge_restore_keeps_journal_when_power_readback_disagrees(self):
        with tempfile.TemporaryDirectory() as folder:
            app = service.Installation(folder, brightness_limit=15)
            fake = FakeBridge([light(1, 5)])
            app.bridge = lambda: fake
            app.data.update(bridge={"id": "test"}, selected=["1"])
            app.control("play", {"scene": {"colors": ["#ff0000"], "brightness": 10}})

            def ignore_power(identifier, state):
                appearance = {k: v for k, v in state.items() if k != "on"}
                fake.lights[0]["state"].update(appearance)

            fake.set_light = ignore_power
            with self.assertRaisesRegex(RuntimeError, "restored power"):
                app.bridge_restore()
            self.assertTrue(app.bridge_journal.exists())

    def test_native_status_retires_only_confirmed_restoration(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "credentials.json"
            net_client.save_credentials(
                config, {"url": "https://192.168.1.2", "token": "a" * 64, "tls_sha256": "b" * 64}
            )
            instance = player.Player({"credentials": str(config)})
            net_client.save_credentials(instance.journal, {"scene": {}, "restored": False})
            with patch.object(
                instance, "command", return_value={"state": "recovery_required", "armed": True}
            ):
                instance.status()
            self.assertFalse(json.loads(instance.journal.read_text())["restored"])
            with patch.object(
                instance, "command", return_value={"state": "restored", "armed": False}
            ):
                instance.status()
            self.assertTrue(json.loads(instance.journal.read_text())["restored"])
            instance.close()

    def test_custom_name_is_reserved_in_both_libraries(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "credentials.json"
            net_client.save_credentials(
                config, {"url": "https://192.168.1.2", "token": "a" * 64, "tls_sha256": "b" * 64}
            )
            owner = studio.Studio({"credentials": str(config)})
            with self.assertRaises(ValueError):
                owner.call("save", {"name": " custom ", "scene": {}})
            self.assertFalse(owner.library.exists())
            owner.close()

    def test_corrupt_host_journal_can_retire_after_firmware_confirms_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "credentials.json"
            net_client.save_credentials(
                config, {"url": "https://192.168.1.2", "token": "a" * 64, "tls_sha256": "b" * 64}
            )
            owner = player.Player({"credentials": str(config)})
            owner.journal.write_text("{broken")
            with patch.object(owner, "command", return_value={"armed": False, "state": "restored"}):
                owner.stop()
            self.assertTrue(json.loads(owner.journal.read_text())["restored"])
            owner.close()


class TransportTests(unittest.TestCase):
    def connection(self, status):
        connection = MagicMock()
        connection.sock.getpeercert.return_value = b"certificate"
        connection.getresponse.return_value.status = status
        connection.getresponse.return_value.read.return_value = b'{"secret":"DO NOT ECHO"}'
        connection.getresponse.return_value.will_close = False
        return connection

    def test_bridge_and_device_denials_have_safe_typed_errors(self):
        pin = hashlib.sha256(b"certificate").hexdigest()
        for status in (401, 403):
            for source in ("bridge", "device"):
                with self.subTest(status=status, source=source):
                    connection = self.connection(status)
                    with patch("http.client.HTTPSConnection", return_value=connection):
                        with self.assertRaises(errors.AuthenticationError) as raised:
                            if source == "bridge":
                                bridge.Bridge(
                                    {"address": "192.168.1.2", "key": "secret", "pin": pin}
                                ).resources("light")
                            else:
                                net_client.PinnedHTTPS(
                                    {
                                        "url": "https://192.168.1.2",
                                        "token": "a" * 64,
                                        "tls_sha256": pin,
                                    }
                                ).call("GET", "/api/status")
                    self.assertEqual(raised.exception.source, source)
                    self.assertNotIn("DO NOT ECHO", str(raised.exception))
                    connection.close.assert_called()

    def test_hostname_resolution_checks_all_answers_and_preserves_private_scope(self):
        with patch.object(
            bridge.socket,
            "getaddrinfo",
            return_value=[(None, None, None, None, ("192.168.1.4", 443))],
        ):
            self.assertEqual(bridge.local_address("hue.local"), "192.168.1.4")
        answers = [
            (None, None, None, None, ("192.168.1.4", 443)),
            (None, None, None, None, ("8.8.8.8", 443)),
        ]
        with (
            patch.object(bridge.socket, "getaddrinfo", return_value=answers),
            self.assertRaises(ValueError),
        ):
            bridge.local_address("hue.local")

    def test_device_certificate_checked_before_token_is_sent(self):
        connection = self.connection(200)
        with patch("http.client.HTTPSConnection", return_value=connection):
            api = net_client.PinnedHTTPS(
                {"url": "https://192.168.1.2", "token": "a" * 64, "tls_sha256": "0" * 64}
            )
            with self.assertRaises(errors.CertificateError):
                api.call("GET", "/api/status")
        connection.request.assert_not_called()
        connection.close.assert_called_once()

    def test_idle_socket_retries_status_once_but_never_repeats_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "credentials.json"
            net_client.save_credentials(
                config, {"url": "https://192.168.1.2", "token": "a" * 64, "tls_sha256": "b" * 64}
            )
            instance = player.Player({"credentials": str(config)})
            with patch.object(
                instance, "command", side_effect=[OSError(), {"armed": False, "state": "idle"}]
            ) as call:
                self.assertEqual(instance.status()["state"], "idle")
                self.assertEqual(call.call_count, 2)
            with (
                patch.object(instance.http, "call", side_effect=OSError()) as call,
                self.assertRaises(OSError),
            ):
                instance.command("player_start")
            self.assertEqual(call.call_count, 1)

    def test_stop_and_release_reconnect_evicted_socket_before_one_write(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "credentials.json"
            net_client.save_credentials(
                config, {"url": "https://192.168.1.2", "token": "a" * 64, "tls_sha256": "b" * 64}
            )
            instance = player.Player({"credentials": str(config)})
            for operation, final in (("stop", "restored"), ("release", "released")):
                with patch.object(
                    instance,
                    "command",
                    side_effect=[
                        OSError("evicted idle connection"),
                        {"armed": False, "state": "idle"},
                        {"ok": True},
                        {"armed": False, "state": final},
                    ],
                ) as command:
                    self.assertEqual(getattr(instance, operation)()["state"], final)
                self.assertEqual(
                    [call.args[0] for call in command.call_args_list],
                    ["player_status", "player_status", "player_" + operation, "player_status"],
                )
            instance.close()


class USBTests(unittest.TestCase):
    def test_provision_saves_token_before_mutation_and_verifies_the_saved_pin(self):
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import wifi_setup

            with tempfile.TemporaryDirectory() as folder:
                credentials = Path(folder) / "device-credentials.json"

                class Link:
                    def __init__(self, port):
                        self.configured = False

                    def request(self, op, **fields):
                        if op == "net_config":
                            saved = json.loads(credentials.read_text())
                            self.assert_saved = (
                                saved["token"] == fields["token"] and saved["url"] is None
                            )
                            assert self.assert_saved
                            self.configured = True
                            return {"ok": True}
                        return {
                            "network": {
                                "supported": True,
                                "tls_sha256": "b" * 64,
                                **({"url": "https://192.168.1.3"} if self.configured else {}),
                            }
                        }

                    def close(self):
                        pass

                api = MagicMock()
                api.call.return_value = {"target": "esp32c6"}
                with (
                    patch.object(wifi_setup, "Link", Link),
                    patch.object(wifi_setup.getpass, "getpass", return_value="private-password"),
                    patch.object(wifi_setup.time, "sleep"),
                    patch.object(wifi_setup, "PinnedHTTPS", return_value=api) as client,
                ):
                    self.assertEqual(
                        wifi_setup.main(
                            ["--port", "fake", "--ssid", "test", "--credentials", str(credentials)]
                        ),
                        0,
                    )
                saved = json.loads(credentials.read_text())
                self.assertEqual(client.call_args.args[0], saved)
                self.assertNotIn("private-password", credentials.read_text())
                self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
        finally:
            sys.path.remove(str(ROOT / "tools"))
