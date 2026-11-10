import copy
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import protocol  # noqa: F401 -- installs aliases for the shipped protocol modules
import bridge
from bridge import bridge_points, writable_state
from player import compile_scene, fit_scene
from service import Installation
from festavia import is_festavia


def light(i, points=1, *, on=False, level=10, color=True):
    state = {"on": {"on": on}, "dimming": {"brightness": level}}
    if color:
        state["color"] = {"xy": {"x": 0.3, "y": 0.3}}
    return {
        "id": str(i),
        "ieee": f"{i:016x}",
        "name": f"Light {i}",
        "model": "test",
        "software": "1",
        "product_name": "Hue Festavia string lights",
        "gradient_points": points,
        "color": color,
        "white": False,
        "dimming": True,
        "reachable": True,
        "state": state,
    }


class FakeBridge:
    def __init__(self, lights):
        self.lights = copy.deepcopy(lights)
        self.calls = []
        self.active = []
        self.fail = None

    def inventory(self):
        return {
            "lights": copy.deepcopy(self.lights),
            "active_entertainment": self.active,
            "gradient_ieees": [l["ieee"] for l in self.lights if l["gradient_points"] > 1],
        }

    def set_light(self, identifier, state):
        self.calls.append((identifier, copy.deepcopy(state)))
        if self.fail == len(self.calls):
            raise RuntimeError("simulated partial write")
        for item in self.lights:
            if item["id"] == identifier:
                item["state"].update(copy.deepcopy(state))
        return {}


class PortableTests(unittest.TestCase):
    def test_festavia_identity_uses_product_or_known_model_not_user_name(self):
        self.assertTrue(is_festavia({"model": "LCX030", "name": "Roof", "product_name": ""}))
        self.assertTrue(
            is_festavia({"model": "unknown", "product_name": "Hue Festavia globe string lights"})
        )
        self.assertFalse(
            is_festavia({"model": "LCA001", "name": "Festavia", "product_name": "Hue color bulb"})
        )
        self.assertFalse(
            is_festavia({"model": "LCX005", "product_name": "Hue gradient lightstrip"})
        )

    def test_layout_scales_without_gaps_or_zero_length_regions(self):
        for count in (1, 2, 3, 4, 5, 9, 16, 27, 50, 100, 255):
            for palette in (1, 2, 3, 4, 9, 17, 27):
                for effect in ("static", "flow", "rainbow", "breathe"):
                    scene = fit_scene(
                        {
                            "positions": count,
                            "effect": effect,
                            "colors": ["#ff0000"] * palette,
                            "brightness": 10,
                        }
                    )
                    layout = scene["layout"]
                    self.assertEqual(
                        [p for a, n in layout for p in range(a, a + n)], list(range(count))
                    )
                    self.assertLessEqual(len(layout), min(10, count))
                    self.assertTrue(all(n >= 1 for _, n in layout))
                    samples, _ = compile_scene(scene, list(range(1, len(layout) + 1)))
                    self.assertTrue(samples)

    def test_bridge_repeats_across_mixed_light_quantities(self):
        for quantities in ((1,), (3,), (5,), (1, 1, 1, 1), (5, 1, 3), (100, 255)):
            for color_count in range(1, 28):
                colors = list(range(color_count))
                lights = [light(i, n) for i, n in enumerate(quantities)]
                self.assertEqual(
                    [c for row in bridge_points(lights, colors) for c in row],
                    [i % color_count for i in range(sum(quantities))],
                )
                self.assertEqual(
                    [c for row in bridge_points(lights, colors, True) for c in row],
                    [i % color_count for i in range(sum(quantities))][::-1],
                )

    def test_address_is_local_literal_and_rejects_proxy_abuse(self):
        self.assertEqual(bridge.local_address("192.168.20.5"), "192.168.20.5")
        for value in (
            "localhost",
            "127.0.0.1",
            "169.254.1.2",
            "8.8.8.8",
            "0.0.0.0",
            "192.168.1.1/path",
            "192.168.1.1:8123",
            "https://192.168.1.1",
            "::1",
            "224.0.0.1",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.local_address(value)

    def test_snapshot_uses_active_white_mode(self):
        snapshot = writable_state(
            {
                "on": {"on": True},
                "color": {"xy": {"x": 0.3, "y": 0.4}},
                "color_temperature": {"mirek": 370, "mirek_valid": True},
            }
        )
        self.assertIn("color_temperature", snapshot)
        self.assertNotIn("color", snapshot)

    def test_bridge_pin_mismatch_closes_before_any_request_or_key(self):
        connection = MagicMock()
        connection.sock.getpeercert.return_value = b"changed certificate"
        with patch("bridge.http.client.HTTPSConnection", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "certificate changed"):
                bridge.Bridge(
                    {"address": "192.168.1.2", "pin": "0" * 64, "key": "private-key"}
                ).resources("light")
        connection.close.assert_called_once()
        connection.request.assert_not_called()


class ServiceTests(unittest.TestCase):
    def test_bridge_start_from_above_limit_captures_and_restores_original(self):
        for fixture in self.fake.lights:
            fixture["state"].update(on={"on": True}, dimming={"brightness": 45})
        self.fake.lights[0]["state"]["gradient"] = {
            "points": [{"color": {"xy": {"x": 0.3, "y": 0.3}}}] * 3
        }
        before = copy.deepcopy(self.fake.lights)
        self.app.control(
            "play", {"scene": {"effect": "static", "colors": ["#ff0000"], "brightness": 10}}
        )
        self.assertTrue(all(body["dimming"]["brightness"] == 10 for _, body in self.fake.calls))
        self.app.control("stop", {})
        self.assertEqual(self.fake.lights, before)

    def test_color_palette_file_corruption_and_invalid_entries_do_not_break_status(self):
        for text in ("{broken", "[]", "null"):
            self.app.palette_library.write_text(text)
            self.assertIn("Christmas", self.app.color_palettes())
        self.app.palette_library.write_text(
            json.dumps({"Valid": ["#FF0000"], "bad": None, "badhex": ["no"], "Custom": ["#ff0000"]})
        )
        self.assertEqual(self.app.color_palettes(), {"Valid": ["#ff0000"]})

    def test_color_palette_is_only_colors_and_does_not_write_lights_or_scenes(self):
        self.app.data["mode"] = "native"
        colors = ["#ff2020", "#00ff00", "#ffdda0"]
        self.app.control("save_palette", {"name": "My colors", "colors": colors, "effect": "flow"})
        saved = json.loads(self.app.palette_library.read_text())
        self.assertEqual(saved["My colors"], colors)
        self.assertFalse(self.app.bridge_library.exists())
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.app.palette_library.stat().st_mode & 0o777, 0o600)
        self.app.control("delete_palette", {"name": "My colors"})
        self.assertNotIn("My colors", self.app.color_palettes())
        self.assertEqual(self.fake.calls, [])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Installation(self.tmp.name, brightness_limit=15)
        self.app.data.update(
            bridge={
                "id": "bridge",
                "address": "192.168.1.2",
                "key": "never-export-this-key",
                "pin": "0" * 64,
                "name": "Bridge",
                "model": "test",
            },
            selected=["1", "2"],
        )
        self.fake = FakeBridge([light(1, 3), light(2, 1, color=False)])
        self.app.bridge = lambda: self.fake

    def tearDown(self):
        self.tmp.cleanup()

    def play(self, **extra):
        return self.app.control(
            "play",
            {"scene": {"colors": ["#ff0000", "#00ff00", "#0000ff"], "brightness": 10, **extra}},
        )

    def test_lease_survives_restart_and_restores_original_off(self):
        original = copy.deepcopy(self.fake.lights)
        self.play()
        self.assertTrue(self.app.bridge_journal.exists())
        restarted = Installation(self.tmp.name, brightness_limit=15)
        restarted.data = self.app.data
        restarted.bridge = lambda: self.fake
        restarted.bridge_restore()
        for before, after in zip(original, self.fake.lights):
            self.assertEqual(after["state"]["on"], before["state"]["on"])
            self.assertEqual(after["state"]["dimming"], before["state"]["dimming"])
        self.assertFalse(restarted.bridge_journal.exists())

    def test_partial_write_failure_recovers_all_selected_lights(self):
        self.fake.fail = 2
        with self.assertRaisesRegex(RuntimeError, "partial write"):
            self.play()
        self.assertTrue(all(not l["state"]["on"]["on"] for l in self.fake.lights))
        self.assertFalse(self.app.bridge_journal.exists())

    def test_external_off_is_preserved(self):
        self.fake.lights[0]["state"]["on"]["on"] = True
        self.play()
        self.fake.lights[0]["state"]["on"]["on"] = False
        self.app.control("stop", {})
        self.assertFalse(self.fake.lights[0]["state"]["on"]["on"])

    def test_bridge_rejects_motion_and_timed_scenes_before_writes(self):
        with self.assertRaises(ValueError):
            self.play(effect="flow")
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.app.bridge_journal.exists())

    def test_brightness_limit_and_nonfinite_values_cannot_be_bypassed(self):
        for value in (15.01, 100, -1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.play(brightness=value)
        self.assertEqual(self.fake.calls, [])

    def test_entertainment_ownership_blocks_writes(self):
        self.fake.active = ["foreign-sync"]
        with self.assertRaises(RuntimeError):
            self.play()
        self.assertEqual(self.fake.calls, [])

    def test_missing_light_retains_recovery_journal(self):
        self.play()
        self.fake.lights.pop()
        with self.assertRaises(RuntimeError):
            self.app.control("stop", {})
        self.assertTrue(self.app.bridge_journal.exists())

    def test_secrets_do_not_appear_in_public_status(self):
        self.assertNotIn("never-export-this-key", json.dumps(self.app.summary()))

    def test_only_festavia_is_visible_but_inventory_keeps_other_gradients(self):
        ordinary = light(3, 5)
        ordinary.update(name="Festavia", product_name="Hue gradient lightstrip")
        self.fake.lights.append(ordinary)
        self.assertEqual([l["id"] for l in self.app.summary()["lights"]], ["1", "2"])
        self.assertIn(ordinary["ieee"], self.app.inventory()["gradient_ieees"])

    def test_non_festavia_and_mixed_target_selection_are_rejected_before_writes(self):
        ordinary = light(3)
        ordinary["product_name"] = "Hue color bulb"
        ordinary["name"] = "Festavia"
        self.fake.lights.append(ordinary)
        for ids in (["3"], ["1", "3"]):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, "Festavia lights only"):
                self.app.setup("select", {"ids": ids, "mode": "bridge"})
        self.assertEqual(self.app.data["selected"], ["1", "2"])
        self.assertEqual(self.fake.calls, [])

    def test_stale_non_festavia_selection_cannot_play_or_apply_uniform(self):
        self.fake.lights[0]["product_name"] = "Hue color bulb"
        status = self.app.summary()
        self.assertEqual(status["selected"], [])
        self.assertTrue(status["selection_requires_update"])
        with self.assertRaisesRegex(ValueError, "Choose your Festavia"):
            self.play()
        with self.assertRaisesRegex(ValueError, "Choose your Festavia"):
            self.app.control("uniform", {"state": {"on": True, "brightness": 25}})
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.app.bridge_journal.exists())

    def test_native_profile_must_match_selected_festavia(self):
        self.app.data.update(mode="native", selected=["1"], native={"ieee": "0000000000009999"})
        with self.assertRaisesRegex(ValueError, "Select your Festavia again"):
            self.play()
        self.assertEqual(self.fake.calls, [])

    def test_native_unknown_model_is_gated_without_zigbee_writes(self):
        with self.assertRaisesRegex(ValueError, "currently verified"):
            self.app.setup("select", {"ids": ["1"], "mode": "native"})
        self.assertEqual(self.fake.calls, [])

    def test_usb_endpoints_are_unavailable_in_home_assistant_runtime(self):
        with self.assertRaisesRegex(ValueError, "Unknown setup"):
            self.app.setup("export-device", {})

    def test_replacing_an_armed_esp_does_not_overwrite_credentials(self):
        client = MagicMock()
        client.call.side_effect = [{"target": "esp32c6"}, {"ok": False}, {"armed": True}]
        config = {
            "target": "esp32c6",
            "url": "https://192.168.1.20",
            "token": "1" * 64,
            "tls_sha256": "2" * 64,
        }
        with patch("service.PinnedHTTPS", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "Stop the existing"):
                self.app.setup("device", {"credentials": config})
        self.assertFalse(self.app.device_path.exists())

    def test_bridge_pair_creates_private_own_key_and_removes_old_selection(self):
        self.app.data["mode"] = "bridge"
        self.app.pending_bridge = {
            "id": "new",
            "address": "192.168.1.4",
            "pin": "a" * 64,
            "name": "New",
            "model": "BSB002",
        }
        with patch("service.Bridge") as client:
            client.return_value.pair.return_value = "new-private-key"
            self.app.setup("pair", {"id": "new"})
        self.assertEqual(self.app.data["selected"], [])
        self.assertEqual(self.app.data["bridge"]["key"], "new-private-key")
        self.assertEqual(self.app.file.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("new-private-key", json.dumps(self.app.summary()))

    def test_dynamic_scene_and_undimmable_output_fail_before_capture(self):
        self.fake.lights[0]["state"]["dynamics"] = {"status": "dynamic_palette"}
        with self.assertRaisesRegex(RuntimeError, "dynamic Hue"):
            self.play()
        self.fake.lights[0]["state"].pop("dynamics")
        self.fake.lights[0]["dimming"] = False
        with self.assertRaisesRegex(ValueError, "cannot dim"):
            self.play()
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.app.bridge_journal.exists())

    def test_effects_are_stopped_then_recovered(self):
        self.fake.lights[0]["state"]["effects"] = {"status": "fire"}
        self.play()
        self.assertEqual(self.fake.calls[0][1]["effects"], {"effect": "no_effect"})
        self.app.control("stop", {})
        self.assertTrue(any(s.get("effects") == {"effect": "fire"} for _, s in self.fake.calls))

    def test_white_is_clamped_to_the_reported_light_range(self):
        self.fake.lights[0]["white"] = True
        self.fake.lights[0]["state"]["color_temperature"] = {
            "mirek_schema": {"mirek_minimum": 200, "mirek_maximum": 400}
        }
        self.app.control("uniform", {"state": {"on": True, "brightness": 25, "mirek": 153}})
        self.assertEqual(self.fake.calls[0][1]["color_temperature"]["mirek"], 200)
