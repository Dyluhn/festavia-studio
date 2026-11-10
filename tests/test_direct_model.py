"""Cross-check the shipped standalone C renderer/programs against the mature host."""

import colorsys
import ctypes as C
import ctypes.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import protocol  # noqa: F401

# protocol registers the pure library aliases before importing player.
# isort: split
import player
from festavia_test_protocol import retained

ROOT = Path(__file__).resolve().parents[1]


class Color(C.Structure):
    _fields_ = [("x", C.c_uint16), ("y", C.c_uint16)]


class Scene(C.Structure):
    _fields_ = [
        ("schema", C.c_uint32),
        ("background", Color * 48),
        ("snake", Color * 9),
        ("pucks", Color * 48),
        *[
            (n, C.c_uint8)
            for n in (
                "background_count",
                "snake_count",
                "effect",
                "brightness",
                "speed",
                "reverse",
                "width",
                "span",
                "phase",
                "cap",
                "smooth",
            )
        ],
    ]


class Snapshot(C.Structure):
    _fields_ = [
        ("on", C.c_bool),
        ("level", C.c_uint8),
        ("mode", C.c_uint8),
        ("capacity", C.c_uint8),
        ("regions", C.c_uint8),
        ("x", C.c_uint16),
        ("y", C.c_uint16),
        ("temperature", C.c_uint16),
        ("aliases", C.c_uint16 * 10),
        ("starts", C.c_uint8 * 10),
        ("lengths", C.c_uint8 * 10),
        ("fc03", C.c_uint8 * 128),
        ("fc03_length", C.c_uint),
    ]


class DirectModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        binary = str(Path(cls.temp.name) / "direct.so")
        source = ROOT / "hue-direct/firmware-source/main"
        args = [
            "cc",
            "-shared",
            "-fPIC",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source / "direct_model.c"),
            str(source / "direct_program.c"),
            str(source / "direct_json.c"),
            str(source / "wire.c"),
        ]
        include = Path(
            os.environ.get(
                "CJSON_SOURCE",
                str(Path(os.environ.get("IDF_PATH", "/nonexistent")) / "components/json/cJSON"),
            )
        )
        if (include / "cJSON.c").exists():
            args += ["-I", str(include), str(include / "cJSON.c")]
        elif Path("/usr/include/cjson/cJSON.h").exists():
            args += ["-I", "/usr/include/cjson", "-lcjson"]
        else:
            raise RuntimeError(
                "Install libcjson-dev or set CJSON_SOURCE to the cJSON source directory"
            )
        subprocess.run(args + ["-lm", "-o", binary], check=True, capture_output=True, text=True)
        cls.lib = C.CDLL(binary)
        cls.lib.hd_entertainment.argtypes = [C.c_char_p, C.c_size_t, C.POINTER(C.c_bool)]
        cls.lib.hd_entertainment.restype = C.c_bool
        cls.lib.hd_defaults.argtypes = [C.POINTER(Scene)]
        cls.lib.hd_scene_valid.argtypes = [C.POINTER(Scene)]
        cls.lib.hd_scene_valid.restype = C.c_bool
        cls.lib.hd_scene_error.argtypes = [C.POINTER(Scene), C.c_uint]
        cls.lib.hd_scene_error.restype = C.c_char_p
        cls.lib.hd_frame.argtypes = [C.POINTER(Scene), C.c_uint, C.c_uint, C.c_void_p]
        cls.lib.hd_frame.restype = C.c_size_t
        cls.lib.hd_frames.argtypes = [C.POINTER(Scene)]
        cls.lib.hd_cycle.argtypes = [C.POINTER(Scene)]
        cls.lib.hd_load_program.argtypes = [C.POINTER(Scene), C.c_uint, C.POINTER(Snapshot)]
        cls.lib.hd_load_program.restype = C.c_void_p
        cls.lib.hd_prepare_program.argtypes = [
            C.POINTER(Scene),
            C.POINTER(Snapshot),
            C.c_char_p,
            C.c_char_p,
            C.c_uint,
            C.c_uint,
            C.c_bool,
        ]
        cls.lib.hd_prepare_program.restype = C.c_void_p
        cls.lib.cJSON_PrintUnformatted.argtypes = [C.c_void_p]
        cls.lib.cJSON_PrintUnformatted.restype = C.c_void_p
        cls.lib.cJSON_Delete.argtypes = [C.c_void_p]
        cls.lib.cJSON_free.argtypes = [C.c_void_p]
        cls.lib.hd_temperature_slot.argtypes = [C.c_uint, C.c_uint]
        cls.lib.hd_slot_temperature.argtypes = [C.c_uint, C.c_uint]
        cls.lib.hd_color_valid.argtypes = [Color]
        cls.lib.hd_color_valid.restype = C.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scene(self):
        s = Scene()
        self.lib.hd_defaults(C.byref(s))
        for i in range(48):
            xy = player.color(
                "#" + "".join(f"{round(c * 255):02x}" for c in colorsys.hsv_to_rgb(i / 48, 1, 1))
            )
            s.background[i] = s.pucks[i] = Color(*(round(v * 65535) for v in xy))
        return s

    def unpack(self, pointer):
        self.assertTrue(pointer)
        text = self.lib.cJSON_PrintUnformatted(pointer)
        try:
            return json.loads(C.string_at(text))
        finally:
            self.lib.cJSON_free(text)
            self.lib.cJSON_Delete(pointer)

    def snapshot(self, count):
        b = Snapshot(
            on=False,
            level=115,
            mode=2,
            capacity=10,
            regions=min(count, 7),
            x=30121,
            y=26905,
            temperature=370,
        )
        for i in range(b.regions):
            b.starts[i], b.lengths[i], b.aliases[i] = (
                i,
                1 if i < b.regions - 1 else count - i,
                100 + i,
            )
        return b

    def test_bridge_inventory_is_validated_without_allocating_a_large_tree(self):
        def check(data, expected, active=False):
            raw = data if isinstance(data, bytes) else json.dumps(data).encode()
            result = C.c_bool(False)
            self.assertEqual(
                self.lib.hd_entertainment(raw, len(raw), C.byref(result)), expected, raw[:200]
            )
            if expected:
                self.assertEqual(result.value, active)

        # The bridge may carry thousands of nested channel fields. Only its
        # top-level resource status controls the observer.
        area = {
            "status": "inactive",
            "channels": [{"status": "active", "positions": [1, 2, 3], "x": 1.5e-2}] * 100,
        }
        check({"errors": [], "data": [area] * 4}, True)
        area["status"] = "active"
        check({"data": [area], "errors": []}, True, True)
        check({"data": [], "errors": []}, True)
        for raw in (
            b'{"data":[],"errors":[{}]}',
            b'{"data":[{}],"errors":[]}',
            b'{"data":[],"errors":[]} trailing',
            b'{"data":[],"data":[],"errors":[]}',
            b'{"data":[{"status":"inactive","x":01}],"errors":[]}',
            b'{"data":[{"status":"inactive","x":"\\q"}],"errors":[]}',
            b'{"data":[{"status":"unknown"}],"errors":[]}',
            b"[]",
        ):
            check(raw, False)
        valid = json.dumps({"data": [area], "errors": []}).encode()
        for i in range(len(valid)):
            check(valid[:i], False)

    def test_all_slider_slots_round_trip_without_hidden_gaps(self):
        for n in (3, 6, 10):
            for i in range(n):
                self.assertEqual(
                    self.lib.hd_temperature_slot(self.lib.hd_slot_temperature(i, n), n), i
                )
        for i in range(1, 101):
            self.assertEqual(self.lib.hd_percent(self.lib.hd_control_level(i)), i)

    def test_actual_hue_v2_wire_brightness_values_select_exact_indices(self):
        # Captured from this bridge's unmodified v2 light API, not generated
        # through our encoder. An old 0..254 decoder skipped indices 1/3/5.
        for percent, wire in (
            (1, 4),
            (2, 6),
            (3, 9),
            (4, 11),
            (5, 14),
            (8, 21),
            (10, 26),
            (16, 41),
            (27, 69),
            (48, 122),
        ):
            self.assertEqual(self.lib.hd_percent(wire), percent)
            self.assertEqual(self.lib.hd_control_level(percent), wire)

    def test_corrupt_scenes_and_invalid_colors_are_rejected(self):
        s = self.scene()
        self.assertTrue(self.lib.hd_scene_valid(C.byref(s)))
        for field, value in (
            ("schema", 0),
            ("background_count", 49),
            ("snake_count", 9),
            ("effect", 10),
            ("speed", 0),
            ("cap", 0),
            ("width", 9),
        ):
            old = getattr(s, field)
            setattr(s, field, value)
            self.assertFalse(self.lib.hd_scene_valid(C.byref(s)), field)
            setattr(s, field, old)
        self.assertFalse(self.lib.hd_color_valid(Color(65535, 65535)))
        self.assertFalse(self.lib.hd_color_valid(Color(0, 0)))

    def test_native_frames_match_existing_renderer_at_every_count(self):
        s = self.scene()
        original_color = player.color
        xy = lambda c: [c[0] / 65535, c[1] / 65535]
        with patch.object(player, "color", xy), patch.object(player, "color_strength", lambda _: 1):
            for positions in range(1, 49):
                for colors in range(1, min(9, positions) + 1):
                    s.background_count = colors
                    palette = [(s.background[i].x, s.background[i].y) for i in range(colors)]
                    for effect, name in enumerate(player.PUCK_EFFECTS):
                        if name == "snake" and positions == 1:
                            continue
                        s.effect = effect
                        s.width = s.snake_count = 1
                        for reverse in (False, True):
                            s.reverse = reverse
                            scene = {
                                "layout_mode": "pucks",
                                "positions": positions,
                                "colors": palette,
                                "effect": name,
                                "brightness": 9,
                                "speed": 1,
                                "reverse": reverse,
                                "smoothing": round(0x400 + s.smooth * (0x4000 - 0x400) / 100),
                            }
                            if name == "snake":
                                scene["snake_colors"] = [(s.snake[0].x, s.snake[0].y)]
                            samples, _ = player.compile_puck_scene(scene)
                            self.assertEqual(self.lib.hd_frames(C.byref(s)), len(samples))
                            for f in {0, len(samples) // 3, len(samples) - 1}:
                                data = (C.c_uint8 * 82)()
                                length = self.lib.hd_frame(C.byref(s), positions, f, data)
                                self.assertEqual(
                                    bytes(data[:length]).hex(),
                                    samples[f],
                                    (positions, colors, name, reverse, f),
                                )
        self.assertIs(player.color, original_color)

    def test_custom_snake_width_phase_and_speed_match_host(self):
        s = self.scene()
        s.effect = 8
        s.brightness = 100
        s.cap = 19
        s.background_count = 3
        s.snake_count = 2
        s.snake[1] = Color(44695, 19005)
        xy = lambda c: [c[0] / 65535, c[1] / 65535]
        with patch.object(player, "color", xy), patch.object(player, "color_strength", lambda _: 1):
            for width in (1, 3, 8):
                s.width = width
                for percent in (1, 5, 17, 100):
                    s.speed = percent
                    for phase in (0, 33, 99):
                        s.phase = phase
                        for reverse in (0, 1):
                            s.reverse = reverse
                            scene = {
                                "layout_mode": "pucks",
                                "positions": 27,
                                "effect": "snake",
                                "colors": [
                                    (s.background[i].x, s.background[i].y) for i in range(3)
                                ],
                                "snake_colors": [
                                    (s.snake[i % 2].x, s.snake[i % 2].y) for i in range(width)
                                ],
                                "brightness": 19,
                                "speed": percent / 5,
                                "phase": phase / 100,
                                "reverse": bool(reverse),
                            }
                            samples, _ = player.compile_puck_scene(scene)
                            self.assertEqual(len(samples), self.lib.hd_frames(C.byref(s)))
                            for f, expected in enumerate(samples):
                                data = (C.c_uint8 * 82)()
                                n = self.lib.hd_frame(C.byref(s), 27, f, data)
                                self.assertEqual(
                                    bytes(data[:n]).hex(),
                                    expected,
                                    (width, percent, phase, reverse, f),
                                )
                                self.assertLessEqual(data[2], 49)

    def test_all_individual_counts_and_reverse_match_finite_host_program(self):
        s = self.scene()
        s.effect = 9
        with (
            patch.object(player, "color", lambda c: [c[0] / 65535, c[1] / 65535]),
            patch.object(player, "color_strength", lambda _: 1),
        ):
            for count in range(1, 49):
                b = self.snapshot(count)
                before = {
                    "logical_count": count,
                    "aliases": list(b.aliases[: b.regions]),
                    "segments": [[b.starts[i], b.lengths[i]] for i in range(b.regions)],
                }
                for reverse in (False, True):
                    s.reverse = reverse
                    actual = self.unpack(self.lib.hd_load_program(C.byref(s), count, C.byref(b)))
                    expected = retained.program(
                        {
                            "positions": count,
                            "colors": [(s.pucks[i].x, s.pucks[i].y) for i in range(count)],
                            "effect": "static",
                            "brightness": 9,
                            "reverse": reverse,
                        },
                        before["aliases"],
                        before,
                    )
                    self.assertEqual(actual["paint"], expected, (count, reverse))
                    self.assertTrue(
                        all(len(bytes.fromhex(p["payload"])) <= 82 for p in actual["paint"])
                    )

    def test_recovery_plan_matches_existing_ownership_and_low_start(self):
        from types import SimpleNamespace

        for count in range(1, 49):
            b = self.snapshot(count)
            s = self.scene()
            actual = self.unpack(
                self.lib.hd_prepare_program(
                    C.byref(s), C.byref(b), b"0017880102030405", b"0102030405060708", 123, 11, True
                )
            )
            before = {
                "logical_count": count,
                "on": False,
                "level": b.level,
                "color": {"3": b.x, "4": b.y, "7": b.temperature, "8": b.mode},
                "aliases": list(b.aliases[: b.regions]),
                "segments": [[b.starts[i], b.lengths[i]] for i in range(b.regions)],
            }
            profile = {
                "ieee": "0017880102030405",
                "extpan": "0102030405060708",
                "hue_takeover": True,
            }
            device = SimpleNamespace(
                address=123, endpoint=11, identity={"5": "LCX030", "16384": "1.163.5"}
            )
            expected = player.recovery_plan(
                profile,
                device,
                before,
                before["segments"],
                before["aliases"],
                startup_level=23,
                native=True,
            )
            self.assertEqual({k: v for k, v in actual.items() if k != "op"}, expected, count)


if __name__ == "__main__":
    unittest.main()
