import json
import struct
import unittest
from pathlib import Path

import protocol  # noqa: F401 -- installs aliases for the shipped protocol modules
from player import CAMERA_LAYOUT, auto_layout, fit_scene, compile_scene, recovery_plan, rgb_xy


class AutoFitTests(unittest.TestCase):
    def test_all_palette_sizes_cover_every_position_without_large_regions(self):
        for effect in ("static", "gradient", "flow", "rainbow", "chase", "wave", "breathe"):
            for count in range(1, 28):
                with self.subTest(effect=effect, colors=count):
                    layout = auto_layout({"effect": effect, "colors": ["#ff0000"] * count})
                    self.assertLessEqual(len(layout), 10)
                    self.assertEqual(
                        [p for a, n in layout for p in range(a, a + n)], list(range(27))
                    )
                    widths = [n for _, n in layout]
                    self.assertLessEqual(max(widths) - min(widths), 1)
                    scene = fit_scene({"effect": effect, "colors": ["#ff0000"] * count})
                    frames, _ = compile_scene(scene, list(range(1, len(layout) + 1)))
                    self.assertTrue(frames)
                    self.assertTrue(
                        all(len(bytes.fromhex(frame)) == 6 + 7 * len(layout) for frame in frames)
                    )
                    if effect == "static" and count <= 10:
                        coverage = [
                            sum(widths[i] for i in range(c, len(layout), count))
                            for c in range(count)
                        ]
                        self.assertLessEqual(max(coverage) - min(coverage), 1)

    def test_three_static_colors_make_nine_equal_full_string_regions(self):
        scene = fit_scene(
            {
                "effect": "static",
                "colors": ["#ff0000", "#00ff00", "#0000ff"],
                "layout": CAMERA_LAYOUT,
            }
        )
        self.assertEqual(scene["layout"], [[i, 3] for i in range(0, 27, 3)])
        self.assertEqual(scene["layout_mode"], "auto")
        frames, _ = compile_scene(scene, list(range(1, 10)))
        raw = bytes.fromhex(frames[0])
        for i in range(9):
            self.assertEqual(raw[10 + 7 * i : 13 + 7 * i], raw[10 + 7 * (i % 3) : 13 + 7 * (i % 3)])

    def test_explicit_custom_maps_and_legacy_custom_frames_remain_exact(self):
        scene = {
            "effect": "static",
            "colors": ["#ff0000"],
            "layout_mode": "custom",
            "layout": CAMERA_LAYOUT,
        }
        self.assertEqual(fit_scene(scene), scene)
        custom = {
            "effect": "custom",
            "layout": CAMERA_LAYOUT,
            "frames": [[{"color": "#ff0000", "brightness": 20}] * 10],
        }
        self.assertEqual(fit_scene(custom)["layout"], CAMERA_LAYOUT)
        self.assertEqual(fit_scene(custom)["layout_mode"], "custom")

    def test_static_large_palette_samples_both_ends(self):
        colors = [f"#ff{i:02x}00" for i in range(27)]
        scene = fit_scene({"effect": "static", "colors": colors})
        frames, _ = compile_scene(scene, list(range(1, 11)))
        last, _ = compile_scene({"effect": "static", "colors": [colors[-1]]}, [10])
        self.assertEqual(bytes.fromhex(frames[0])[-3:], bytes.fromhex(last[0])[-3:])

    def test_flow_uses_position_distance_instead_of_region_index(self):
        scene = {
            "effect": "flow",
            "colors": ["#ff0000", "#00ff00", "#0000ff"],
            "layout": [[0, 1], [1, 1], [2, 25]],
            "layout_mode": "custom",
        }
        frames, _ = compile_scene(scene, [1, 2, 3])
        raw = bytes.fromhex(frames[0])
        self.assertEqual(raw[10:13], raw[17:20])
        self.assertNotEqual(raw[10:13], raw[24:27])


class SceneTests(unittest.TestCase):
    def test_all_effects_send_complete_maps_with_valid_xy_and_brightness(self):
        aliases = list(range(0x69D3, 0x69DA))
        for effect in ("static", "rainbow", "chase", "wave", "breathe", "gradient", "flow"):
            with self.subTest(effect=effect):
                samples, fps = compile_scene(
                    {"effect": effect, "brightness": 20, "fps": 25}, aliases
                )
                self.assertTrue(1 <= len(samples) <= 64)
                self.assertEqual(fps, 25)
                for sample in samples:
                    raw = bytes.fromhex(sample)
                    self.assertEqual(len(raw), 6 + 7 * len(aliases))
                    self.assertEqual(
                        [struct.unpack_from("<H", raw, 6 + 7 * i)[0] for i in range(len(aliases))],
                        aliases,
                    )
                    self.assertTrue(
                        all(
                            0 <= struct.unpack_from("<H", raw, 8 + 7 * i)[0] >> 5 <= 409
                            for i in range(len(aliases))
                        )
                    )

    def test_flow_moves_the_palette_left_with_every_region_at_ten_percent(self):
        aliases = list(range(1, 11))
        scene = {
            "effect": "flow",
            "colors": ["#ff2020", "#ffdda0", "#d6eaff"],
            "brightness": 10,
            "fps": 15,
        }
        frames, _ = compile_scene(scene, aliases)
        self.assertEqual(len(frames), 60)
        for sample in frames:
            raw = bytes.fromhex(sample)
            self.assertEqual(len(raw), 76)
            self.assertEqual(
                [struct.unpack_from("<H", raw, 8 + 7 * i)[0] >> 5 for i in range(10)],
                [205] * 10,
            )
        # After 1/10 cycle, each color has moved to the next higher index (left).
        for f in range(len(frames)):
            before = bytes.fromhex(frames[f])
            after = bytes.fromhex(frames[(f + 6) % len(frames)])
            for i in range(10):
                target = (i + 1) % 10
                self.assertEqual(
                    before[10 + 7 * i : 13 + 7 * i], after[10 + 7 * target : 13 + 7 * target]
                )

    def test_flow_reverse_moves_right_and_preserves_alias_order(self):
        scene = {"effect": "flow", "colors": ["#ff2020", "#d6eaff"], "fps": 15}
        aliases = list(range(1, 11))
        normal, _ = compile_scene(scene, aliases)
        reverse, _ = compile_scene({**scene, "reverse": True}, aliases)
        self.assertEqual(normal[0], reverse[0])
        for f, frame in enumerate(reverse):
            self.assertEqual(frame, normal[-f % len(normal)])
            raw = bytes.fromhex(frame)
            self.assertEqual(
                [struct.unpack_from("<H", raw, 6 + 7 * i)[0] for i in range(10)], aliases
            )

    def test_flow_single_color_remains_constant_across_the_wrap(self):
        frames, _ = compile_scene({"effect": "flow", "colors": ["#ff2020"]}, [1, 2])
        self.assertEqual(len(set(frames)), 1)

    def test_flow_phase_wraps_safely_with_longer_palettes(self):
        for phase in (-100, -0.3, 0, 0.1, 0.2, 0.7, 100):
            for reverse in (False, True):
                with self.subTest(phase=phase, reverse=reverse):
                    frames, _ = compile_scene(
                        {
                            "effect": "flow",
                            "phase": phase,
                            "reverse": reverse,
                            "fps": 15,
                            "colors": ["#ff0000", "#00ff00", "#0000ff", "#ffffff"],
                        },
                        list(range(1, 11)),
                    )
                    self.assertEqual(len(frames), 60)
                    self.assertTrue(all(len(bytes.fromhex(f)) == 76 for f in frames))

    def test_27_record_full_scene_is_195_bytes(self):
        samples, _ = compile_scene({"effect": "rainbow"}, list(range(1, 28)))
        self.assertEqual(len(bytes.fromhex(samples[0])), 195)

    def test_custom_regions_have_independent_zero_and_brightness(self):
        samples, _ = compile_scene(
            {
                "effect": "custom",
                "frames": [
                    [
                        {"color": "#00ffff", "brightness": 0},
                        {"color": "#ff00ff", "brightness": 35},
                    ]
                ],
            },
            [1, 2],
        )
        raw = bytes.fromhex(samples[0])
        self.assertEqual(struct.unpack_from("<H", raw, 8)[0], 0)
        self.assertEqual(struct.unpack_from("<H", raw, 15)[0] >> 5, round(35 * 20.47))
        with self.assertRaises(ValueError):
            compile_scene(
                {
                    "effect": "custom",
                    "frames": [[{"color": "#00ffff", "brightness": 0}]],
                },
                [1, 2],
            )

    def test_custom_master_dimmer_scales_without_changing_other_region_settings(self):
        scene = {
            "effect": "custom",
            "brightness": 50,
            "frames": [[{"color": "#00ffff", "brightness": 20}]],
        }
        samples, _ = compile_scene(scene, [1])
        raw = bytes.fromhex(samples[0])
        self.assertEqual(struct.unpack_from("<H", raw, 8)[0] >> 5, 205)

    def test_reverse_mirrors_static_gradient_and_custom_states_without_moving_aliases(
        self,
    ):
        aliases = [1, 2, 3]
        for effect in ("static", "gradient"):
            scene = {"effect": effect, "colors": ["#00ffff", "#ff00ff", "#ffaa00"]}
            normal, _ = compile_scene(scene, aliases)
            reverse, _ = compile_scene({**scene, "reverse": True}, aliases)
            a, b = bytes.fromhex(normal[0]), bytes.fromhex(reverse[0])
            self.assertEqual(a[10:13], b[24:27])
            self.assertEqual([struct.unpack_from("<H", b, 6 + 7 * i)[0] for i in range(3)], aliases)
        scene = {
            "effect": "custom",
            "reverse": True,
            "frames": [
                [
                    {"color": "#00ffff", "brightness": 0},
                    {"color": "#ff00ff", "brightness": 20},
                    {"color": "#ffaa00", "brightness": 50},
                ]
            ],
        }
        frames, _ = compile_scene(scene, aliases)
        raw = bytes.fromhex(frames[0])
        self.assertEqual(struct.unpack_from("<H", raw, 8)[0] >> 5, 1024)
        self.assertEqual(struct.unpack_from("<H", raw, 22)[0] >> 5, 0)

    def test_native_effect_guard_parses_prefix_with_all_fixed_width_fields(self):
        from control_core import snapshot_effect

        self.assertEqual(snapshot_effect({"fc03": "07020134720100"}), 0)
        self.assertEqual(snapshot_effect({"fc03": "2702013472010300"}), 3)
        self.assertEqual(snapshot_effect({"fc03": "3f0001347201aabbccdd0a000100"}), 1)
        with self.assertRaisesRegex(ValueError, "truncated"):
            snapshot_effect({"fc03": "2000"})

    def test_invalid_and_nonfinite_settings_rejected_before_mutation(self):
        for scene in (
            {"brightness": float("nan")},
            {"fps": 26},
            {"speed": 0},
            {"colors": []},
            {"effect": "unknown"},
            {"frames": [], "effect": "custom"},
            {"surprise": 1},
        ):
            with self.subTest(scene=scene), self.assertRaises((ValueError, TypeError)):
                compile_scene(scene, [1])

    def test_recovery_capsule_stops_stream_then_restores_and_verifies(self):
        before = {
            "segments": [[0, 3]],
            "logical_count": 3,
            "aliases": [1],
            "on": True,
            "level": 52,
            "color": {"3": 30121, "4": 26905, "7": 370, "8": 2},
        }
        d = type("D", (), {"endpoint": 11, "identity": {"5": "LCX030", "16384": "1.163.5"}})()
        plan = recovery_plan(
            {"ieee": "0017880100000001", "extpan": "0123456789abcdef"},
            d,
            before,
            [[0, 1], [1, 2]],
            [1, 2],
        )
        self.assertEqual((plan["restore"][0]["cluster"], plan["restore"][0]["command"]), (6, 0))
        self.assertEqual(plan["restore"][1]["payload"], "000100000000")
        self.assertEqual(len(plan["verify"]), 5)
        self.assertEqual(plan["ready"][0]["expect"], "00000200010102")
        self.assertEqual(plan["restore"][-1]["command"], 1)
        self.assertEqual((plan["setup"][0]["cluster"], plan["setup"][0]["command"]), (6, 0))
        level_index = next(i for i, p in enumerate(plan["setup"]) if p["cluster"] == 8)
        on_index = next(
            i for i, p in enumerate(plan["setup"]) if p["cluster"] == 6 and p["command"] == 1
        )
        self.assertLess(level_index, on_index)
        json.dumps(plan, allow_nan=False)

    def test_rgb_black_and_white_have_valid_whitepoints(self):
        for rgb in ([0, 0, 0], [1, 1, 1], [1, 0, 0], [0, 1, 0], [0, 0, 1]):
            x, y = rgb_xy(rgb)
            self.assertTrue(0 <= x <= 0.7347 and 0 <= y <= 0.8264)

    def test_default_interpolation_bridges_radio_delivery_gaps(self):
        frames, _ = compile_scene({"effect": "rainbow"}, [1, 2])
        self.assertEqual(struct.unpack_from("<H", bytes.fromhex(frames[0]), 4)[0], 0x1800)
        explicit, _ = compile_scene({"smoothing": 0x0400}, [1, 2])
        self.assertEqual(struct.unpack_from("<H", bytes.fromhex(explicit[0]), 4)[0], 0x0400)

    def test_rgb_tone_scales_the_dimmer_and_black_is_dark(self):
        scene = {
            "effect": "static",
            "brightness": 100,
            "colors": ["#ff0000", "#800000", "#000000", [0.3, 0.3]],
        }
        frames, _ = compile_scene(scene, [1, 2, 3, 4])
        raw = bytes.fromhex(frames[0])
        levels = [struct.unpack_from("<H", raw, 8 + 7 * i)[0] >> 5 for i in range(4)]
        self.assertEqual(levels, [2047, round(2047 * 128 / 255), 0, 2047])
        self.assertEqual(raw[10:13], raw[17:20])  # Red hue is unchanged by tone.

    def test_black_gradient_fades_red_without_introducing_white(self):
        scene = {"effect": "gradient", "brightness": 100, "colors": ["#ff0000", "#000000"]}
        frames, _ = compile_scene(scene, [1, 2, 3])
        raw = bytes.fromhex(frames[0])
        self.assertEqual(
            [struct.unpack_from("<H", raw, 8 + 7 * i)[0] >> 5 for i in range(3)], [2047, 1024, 0]
        )
        self.assertEqual(raw[10:13], raw[17:20])

    def test_dark_colors_keep_their_dimming_in_every_effect(self):
        for effect in ("static", "gradient", "flow", "chase", "wave", "breathe"):
            with self.subTest(effect=effect):
                frames, _ = compile_scene(
                    {"effect": effect, "brightness": 100, "colors": ["#000000"]}, [1, 2]
                )
                for frame in frames:
                    raw = bytes.fromhex(frame)
                    self.assertEqual(
                        [struct.unpack_from("<H", raw, 8 + 7 * i)[0] >> 5 for i in range(2)], [0, 0]
                    )

    def test_custom_rgb_tone_multiplies_region_and_master_dimmers(self):
        frames, _ = compile_scene(
            {
                "effect": "custom",
                "brightness": 50,
                "frames": [
                    [
                        {"color": "#800000", "brightness": 40},
                        {"color": "#000000", "brightness": 100},
                    ]
                ],
            },
            [1, 2],
        )
        raw = bytes.fromhex(frames[0])
        self.assertEqual(
            struct.unpack_from("<H", raw, 8)[0] >> 5, round(40 * 20.47 * 0.5 * 128 / 255)
        )
        self.assertEqual(struct.unpack_from("<H", raw, 15)[0] >> 5, 0)


class AliasAndOwnershipTests(unittest.TestCase):
    def test_live_gradient_inventory_skips_other_fixture_aliases(self):

        from player import virtual_aliases

        links = []

        class FakeDevice:
            ieee = "target"
            endpoint = 11

            def __init__(self, *args, **kwargs):
                self.address = 300
                self.link = kwargs.get("link", object())
                links.append(self.link)

            def connect(self):
                pass

            def close(self):
                pass

            def command(self, cluster, command, payload, manufacturer):
                bank = payload[0]
                values = {0: [100], 1: [101], 2: [], 3: []}[bank]
                raw = bytes([0, bank, len(values)]) + struct.pack("<" + "H" * len(values), *values)
                return {"received": {"payload": raw.hex()}}

        aliases = virtual_aliases(
            {
                "credentials": "private",
                "gradient_inventory_provider": lambda: {
                    "gradient_ieees": ["target", "other"],
                    "active_entertainment": [],
                },
            },
            FakeDevice(),
            {"aliases": [1, 2, 3, 4, 5, 6, 7]},
            {"esp32": {"address": 100}},
            10,
        )
        self.assertEqual(aliases, [1, 2, 3, 4, 5, 6, 7, 102, 103, 104])
        self.assertIs(links[0], links[1], "Peer survey must reuse one TLS transport")

    def test_eight_region_mode_uses_only_own_address_without_provider(self):
        from player import virtual_aliases

        d = type("D", (), {"ieee": "target", "endpoint": 11})()
        before = {"aliases": [1, 2, 3, 4, 5, 6, 7]}
        identity = {"esp32": {"address": 100}}
        self.assertEqual(virtual_aliases({}, d, before, identity, 8), before["aliases"] + [100])
        with self.assertRaises(RuntimeError):
            virtual_aliases({}, d, before, identity, 10)

    def test_active_hue_entertainment_blocks_alias_changes(self):

        from player import virtual_aliases

        with self.assertRaises(RuntimeError):
            virtual_aliases(
                {
                    "gradient_inventory_provider": lambda: {
                        "gradient_ieees": ["target"],
                        "active_entertainment": ["active"],
                    }
                },
                type("D", (), {"ieee": "target"})(),
                {"aliases": list(range(1, 8))},
                {"esp32": {"address": 100}},
                10,
            )

    def test_slow_effect_cycle_is_independent_of_radio_cadence(self):
        from player import cycle_duration

        samples, fps = compile_scene({"effect": "rainbow", "speed": 0.1, "fps": 25}, [1, 2])
        self.assertEqual(len(samples), 64)
        self.assertEqual(
            cycle_duration({"effect": "rainbow", "speed": 0.1}, len(samples), fps),
            40000,
        )

    def test_parallel_starts_are_rejected_before_reading_or_writing_device(self):
        import fcntl
        import tempfile

        from player import Player

        with tempfile.TemporaryDirectory() as tmp:
            p = Player.__new__(Player)
            p.profile = {"credentials": str(Path(tmp) / "private.json")}
            with (Path(tmp) / "player-operation.lock").open("a+") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, "another playback"):
                    p.play({"effect": "static"})
