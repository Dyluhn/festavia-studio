"""Count discovery and compatibility checks using production setup/encoders."""

import json
from pathlib import Path
import tempfile
import unittest
import protocol  # noqa: F401
from festavia_test_protocol.sizing import discovered_size, MAX_PAINT_STEPS
from festavia_test_protocol.errors import PlaybackBlocked
from player import Player, compile_puck_scene


class SizingTests(unittest.TestCase):
    def test_device_and_hue_counts_agree_for_full_and_cut_strings(self):
        for count in (1, 16, 27, 32, 48, 80, 255):
            before = {"logical_count": count, "segments": [[0, count]], "aliases": [77]}
            for light in ({}, {"reported_pixels": count}):
                self.assertEqual(discovered_size(light, before, {}, 10), count)
            with self.assertRaisesRegex(ValueError, "disagree"):
                discovered_size({"reported_pixels": count + 1}, before, {}, 10)
        self.assertEqual(MAX_PAINT_STEPS, 106)

    def test_incomplete_ambiguous_and_unencodable_maps_reject(self):
        for before in (
            {"logical_count": 32, "segments": [[1, 31]], "aliases": [77]},
            {"logical_count": 32, "segments": [[0, 31]], "aliases": [77]},
            {"logical_count": 32, "segments": [[0, 16], [16, 16]], "aliases": [77, 77]},
            {"logical_count": 256, "segments": [[0, 256]], "aliases": [77]},
        ):
            with self.assertRaises(ValueError):
                discovered_size({}, before, {}, 10)

    def test_every_native_animation_compiles_for_each_kit_without_length_overflow(self):
        from player import PUCK_EFFECTS

        for positions in (16, 32, 48, 80, 255):
            for effect in PUCK_EFFECTS:
                samples, _ = compile_puck_scene(
                    {
                        "positions": positions,
                        "effect": effect,
                        "colors": ["#ff0000", "#00ff00", "#0000ff"],
                        "snake_colors": ["#ffffff"],
                        "brightness": 9,
                    }
                )
                for sample in samples:
                    raw = bytes.fromhex(sample)
                    self.assertEqual(raw[-2:], b"\0\0")
                    self.assertLessEqual(len(raw), 39)
                    self.assertLessEqual(raw[2], 25)

    def test_old_firmware_is_compatible_and_larger_size_blocks_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Player.__new__(Player)
            p.profile = {"credentials": str(Path(directory) / "credentials.json")}
            count = 27
            p.journal.write_text(
                json.dumps({"aliases": [77], "layout": [[i, 1] for i in range(count)]})
            )
            state = {"armed": True, "playing": True, "native_palette_supported": True}
            p.status = lambda: state
            writes = []
            p.command = lambda op, **data: writes.append((op, data)) or state
            p.start_scene = lambda *args: state
            scene = {
                "layout_mode": "pucks",
                "positions": 27,
                "colors": ["#ff0000"],
                "brightness": 9,
            }
            p._play(scene)
            self.assertEqual(bytes.fromhex(writes[0][1]["samples"][0])[-2:], b"\xd8\0")
            writes.clear()
            with self.assertRaises(PlaybackBlocked) as error:
                p._play({**scene, "positions": 48})
            self.assertEqual(error.exception.reason, "sizing_update_required")
            self.assertEqual(writes, [])

    def test_aborted_paint_never_reports_success_after_automatic_hue_release(self):
        for state in (
            {"state": "releasing", "reason": "delivery_failed"},
            {"state": "released", "reason": "hue_takeover", "failure_cause": "paint_reply_timeout"},
        ):
            p = Player.__new__(Player)
            p.command = lambda *args, **kwargs: {**state, "playing": False, "applying": False}
            with self.assertRaises(PlaybackBlocked) as error:
                p.start_scene(0, True)
            self.assertEqual(error.exception.reason, "paint_failed")
