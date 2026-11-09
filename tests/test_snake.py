"""Behavioral checks for a moving foreground over a stationary background."""

import unittest

import protocol  # noqa: F401
from player import color, compile_puck_scene, scattered_index, snake_period, snake_sample
from hue_mesh import pack_xy


class SnakeTests(unittest.TestCase):
    def scene(self, **changes):
        return {
            "layout_mode": "pucks",
            "positions": 27,
            "effect": "snake",
            "colors": ["#ff0000", "#00ff00", "#0000ff"],
            "snake_colors": ["#ffffff", "#ff8000"],
            "brightness": 9,
            "fps": 9,
            **changes,
        }

    def test_background_returns_in_place_for_every_length_and_both_directions(self):
        choices = self.scene()["colors"] * 3
        for n in range(1, 10):
            for reverse in (False, True):
                scene = self.scene(colors=choices[:n], reverse=reverse)
                period = snake_period(scene)
                self.assertEqual(period % n, 0)
                for length in range(1, period):
                    scene["snake_colors"] = ["#ffffff", "#ff8000"] * 4
                    scene["snake_colors"] = scene["snake_colors"][:length]
                    for step in range(period):
                        actual = snake_sample(scene, step / period)
                        for puck in range(period):
                            origin = (puck + (1 if reverse else -1) * step) % period
                            expected = (
                                scene["snake_colors"][origin]
                                if origin < length
                                else scene["colors"][puck % n]
                            )
                            for a, b in zip(actual[puck], color(expected)):
                                self.assertAlmostEqual(a, b)
                self.assertEqual(snake_sample(scene, 0), snake_sample(scene, 1))

    def test_crossfade_leaves_uncovered_background_exactly_stationary(self):
        scene = self.scene()
        start = snake_sample(scene, 0)
        end = snake_sample(scene, 1 / 9)
        middle = snake_sample(scene, 0.5 / 9)
        for puck in range(9):
            for k in range(2):
                self.assertAlmostEqual(middle[puck][k], (start[puck][k] + end[puck][k]) / 2)
        for puck in range(3, 9):
            self.assertEqual(middle[puck], color(scene["colors"][puck % 3]))

    def test_wire_frames_preserve_order_compensation_low_level_and_external_off(self):
        scene = self.scene()
        samples, fps = compile_puck_scene(scene)
        self.assertEqual(fps, 9)
        self.assertEqual(len(samples), 36)
        for f, sample in enumerate(samples):
            raw = bytes.fromhex(sample)
            self.assertEqual(raw[:3], bytes([0x52, 1, 23]))
            self.assertEqual(raw[3:5], b"\x01\x00")
            self.assertEqual(raw[6] >> 4, 9)
            self.assertEqual(raw[-2:], bytes([216, 0]))
            actual = snake_sample(scene, f / len(samples))
            for puck in range(27):
                slot = scattered_index(puck % 9, 9)
                self.assertEqual(raw[10 + 3 * slot : 13 + 3 * slot], pack_xy(*actual[puck % 9]))

    def test_invalid_foreground_and_no_background_gap_are_rejected(self):
        for foreground in ([], ["#ffffff"] * 9, ["#010101"], ["#000000"], "#ffffff"):
            with self.subTest(foreground=foreground), self.assertRaises((ValueError, TypeError)):
                compile_puck_scene(self.scene(snake_colors=foreground))
        with self.assertRaises(ValueError):
            compile_puck_scene(self.scene(positions=1, colors=["#ff0000"]))

    def test_direction_matches_existing_flow_for_the_same_visible_pattern(self):
        for reverse in (False, True):
            snake, _ = compile_puck_scene(
                self.scene(colors=["#0000ff"], snake_colors=["#ffffff"], reverse=reverse)
            )
            flow, _ = compile_puck_scene(
                self.scene(effect="flow", colors=["#ffffff"] + ["#0000ff"] * 8, reverse=reverse)
            )
            for a, b in zip(snake, flow):
                self.assertEqual(bytes.fromhex(a)[5:], bytes.fromhex(b)[5:])

    def test_slow_snake_transitions_cover_the_longer_sample_interval(self):
        samples, _ = compile_puck_scene(self.scene(speed=0.1))
        self.assertEqual(len(samples), 64)
        self.assertTrue(all(bytes.fromhex(sample)[3:5] == b"\x06\x00" for sample in samples))
