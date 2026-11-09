"""Acceptance of the packaged HA protocol library without importing HA."""

import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
from protocol import service, player
from test_portable import FakeBridge, light


class NativeLibraryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = service.Installation(self.folder.name, brightness_limit=15)
        self.app.data.update(bridge={"id": "private", "key": "private"}, selected=["1"])
        self.bridge = FakeBridge([light(1, 5)])
        self.bridge.lights[0]["state"]["gradient"] = {
            "points": [{"color": {"xy": {"x": 0.3, "y": 0.3}}}] * 5
        }
        self.app.bridge = lambda: self.bridge

    def tearDown(self):
        self.folder.cleanup()

    def test_bridge_palette_reported_count_and_restore(self):
        before = json.loads(json.dumps(self.bridge.lights[0]["state"]))
        self.app.control(
            "play", {"scene": {"colors": ["#ff0000", "#00ff00", "#0000ff"], "brightness": 10}}
        )
        self.assertEqual(len(self.bridge.lights[0]["state"]["gradient"]["points"]), 5)
        self.app.control("stop", {})
        self.assertEqual(self.bridge.lights[0]["state"], before)

    def test_brightness_rejected_before_write(self):
        with self.assertRaises(ValueError):
            self.app.control("play", {"scene": {"colors": ["#ff0000"], "brightness": 20}})
        self.assertEqual(self.bridge.calls, [])

    def test_no_web_server(self):
        from protocol import studio

        self.assertFalse(hasattr(studio, "create_server"))
        self.assertFalse(hasattr(studio, "serve"))

    def test_bundled_firmware(self):
        import hashlib

        manifest = json.loads((service.RELEASE / "manifest.json").read_text())
        image = manifest["targets"]["esp32c6"]["app"]
        self.assertEqual(
            hashlib.sha256((service.RELEASE / image).read_bytes()).hexdigest(),
            manifest["sha256"][image],
        )

    def test_mapping_scales_for_multiple_palette_sizes(self):
        for count in (9, 27):
            for colors in (
                ["#ff0000"],
                ["#ff0000", "#00ff00", "#0000ff"],
                ["#ff0000", "#00ff00", "#0000ff", "#ffff00"],
            ):
                scene = player.fit_scene(
                    {
                        "layout_mode": "pucks",
                        "positions": count,
                        "colors": colors,
                        "effect": "static",
                        "brightness": 10,
                        "fps": 10,
                    }
                )
                self.assertTrue(
                    player.compile_scene(scene, list(range(1, len(scene["layout"]) + 1)))
                )
                self.assertEqual(sum(n for _, n in scene["layout"]), count)
