"""Verify the finite renderer against an independently modeled lamp framebuffer."""

import colorsys
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import protocol  # noqa: F401
from festavia_test_protocol.retained import program
from player import compile_puck_scene, color, geometry_checks
from hue_mesh import pack_xy

ROOT = Path(__file__).resolve().parents[1]


def fixture(positions=27, count=27, reverse=False, capacity=10):
    colors = [
        "#" + "".join(f"{round(v * 255):02x}" for v in colorsys.hsv_to_rgb(i / count, 1, 1))
        for i in range(count)
    ]
    scene = {
        "layout_mode": "pucks",
        "positions": positions,
        "colors": colors,
        "effect": "static",
        "brightness": 9,
        "reverse": reverse,
    }
    before = {"logical_count": positions, "segments": [[0, positions]], "aliases": [77]}
    return scene, before, program(scene, list(range(101, 101 + capacity)), before)


class RetainedTests(unittest.TestCase):
    def test_peer_survey_is_followed_by_a_safe_read_before_loading_edits(self):
        from player import Player
        import json

        scene, before, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            p = Player.__new__(Player)
            p.profile = {"credentials": str(Path(directory) / "credentials.json")}
            p.journal.write_text(
                json.dumps(
                    {"before": before, "aliases": [77], "layout": [[i, 1] for i in range(27)]}
                )
            )
            events = []
            state = {
                "armed": True,
                "playing": True,
                "native_palette_supported": True,
                "retained_pucks_supported": True,
            }
            p.status = lambda: events.append("read") or state
            p.retained_options = lambda *args, **kwargs: (
                events.append("survey") or {"transport": "retained", "paint": [None] * 16}
            )
            p.command = lambda op, **kw: events.append(op) or state
            p.start_scene = lambda *args: events.append("start") or state
            p._play(scene)
            self.assertEqual(events, ["read", "survey", "read", "player_load", "start"])

    def test_every_count_and_direction_preserves_exact_order_and_original_geometry(self):
        for positions in (11, 16, 21, 24, 27, 31, 32, 48, 80, 255):
            for count in sorted({10, min(16, positions), positions}):
                for reverse in (False, True):
                    scene, before, packets = fixture(positions, count, reverse)
                    framebuffer = [None] * positions
                    aliases = []
                    regions = []
                    self.assertLessEqual(len(packets), 106)
                    for p in packets:
                        data = bytes.fromhex(p["payload"])
                        self.assertLessEqual(len(data) + 5, 82)
                        if p["command"] == 7:
                            aliases = list(struct.unpack("<" + "H" * data[1], data[2:]))
                        elif p["command"] == 5:
                            regions = list(zip(data[2::2], data[3::2]))
                            coverage = {
                                i for start, length in regions for i in range(start, start + length)
                            }
                            self.assertEqual(coverage, set(range(positions)))
                        elif p["command"] == 1:
                            for offset in range(6, len(data), 7):
                                alias, brightness = struct.unpack_from("<HH", data, offset)
                                start, length = regions[aliases.index(alias)]
                                self.assertEqual(length, 1)
                                self.assertEqual(brightness & 31, 0)
                                framebuffer[start] = (
                                    brightness >> 5,
                                    data[offset + 4 : offset + 7],
                                )
                    expected = [
                        pack_xy(
                            *color(scene["colors"][((positions - 1 - i) if reverse else i) % count])
                        )
                        for i in range(positions)
                    ]
                    self.assertEqual([xy for level, xy in framebuffer], expected)
                    self.assertEqual(regions, [(0, positions)])
                    self.assertEqual(aliases, before["aliases"])

    def test_large_palettes_are_static_and_never_become_a_map_animation(self):
        scene, _, _ = fixture()
        samples, fps = compile_puck_scene(scene)
        self.assertEqual(samples, ["000000000004"])
        self.assertEqual(fps, 1)
        with self.assertRaisesRegex(ValueError, "Static repeat"):
            compile_puck_scene({**scene, "effect": "flow"})

    def test_gapped_original_layout_is_rejected_before_writing(self):
        scene, before, _ = fixture()
        before["segments"] = [[0, 10], [11, 16]]
        before["aliases"] = [77, 78]
        with self.assertRaisesRegex(ValueError, "cover every puck"):
            program(scene, list(range(101, 111)), before)

    def test_original_seven_aliases_paint_all27_without_allocating_identifiers(self):
        scene, before, _ = fixture()
        before["aliases"] = list(range(101, 108))
        before["segments"] = [[0, 3], [3, 3], [6, 5], [11, 5], [16, 5], [21, 3], [24, 3]]
        packets = program(scene, before["aliases"], before)
        self.assertEqual(len(packets), 16)
        self.assertEqual(sum(p["command"] == 1 for p in packets), 6)
        for p in packets:
            if p["command"] == 7:
                self.assertEqual(
                    bytes.fromhex(p["payload"])[2:], struct.pack("<7H", *before["aliases"])
                )

    def test_owned_edits_reuse_addresses_and_only_refresh_entertainment_ownership(self):
        from player import Player
        from unittest.mock import patch

        scene, before, _ = fixture()
        before.update(
            aliases=list(range(101, 108)),
            segments=[[0, 3], [3, 3], [6, 5], [11, 5], [16, 5], [21, 3], [24, 3]],
        )
        p = Player.__new__(Player)
        p.profile = {"ieee": "target", "active_entertainment_provider": lambda: []}
        identity = {"identity": {"5": "LCX030", "16384": "1.163.5"}}
        with patch(
            "festavia_test_protocol.player.connected",
            side_effect=AssertionError("no raw connection for an owned edit"),
        ):
            options = p.retained_options(scene, before, identity=identity)
            self.assertEqual(len(options["paint"]), 16)
            p.profile["active_entertainment_provider"] = lambda: ["Hue Sync"]
            with self.assertRaisesRegex(RuntimeError, "entertainment is already active"):
                p.retained_options(scene, before, identity=identity)

    def test_real_c_player_paint_reply_failure_idle_and_handoff_boundaries(self):
        for positions in (11, 16, 27, 32, 48, 80, 255):
            self.run_c_fixture(positions)
            if positions in (48, 255):
                self.run_c_fixture(positions, capacity=7)

    def run_c_fixture(self, positions, capacity=10):
        _, before, packets = fixture(positions, positions, capacity=capacity)
        import json

        request = {
            "op": "player_load",
            "samples": ["000000000004"],
            "fps": 1,
            "transport": "retained",
            "positions": positions,
            "paint": packets,
        }
        self.assertLessEqual(len(json.dumps(request).encode()), 40000)
        if positions == 255 and capacity == 7:
            self.assertEqual(len(packets), 106)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)

            def cpacket(p):
                raw = bytes.fromhex(p["payload"])
                expect = bytes.fromhex(p.get("expect", ""))
                fields = {
                    "cluster": p["cluster"],
                    "command": p["command"],
                    "type": p["frame_type"],
                    "manufacturer": p["manufacturer"],
                    "length": len(raw),
                    "expected_length": len(expect),
                    "response_command": p.get("response_command", 0),
                }
                return (
                    "{"
                    + ",".join("." + k + "=" + str(v) for k, v in fields.items())
                    + ",.payload={"
                    + ",".join(map(str, raw))
                    + "},.expected={"
                    + ",".join(map(str, expect))
                    + "}}"
                )

            checks = geometry_checks(before["segments"], before["aliases"])
            (folder / "retained_fixture.h").write_text(
                f"#define FIXTURE_POSITIONS {positions}\nstatic const packet_t fixture_paint[]={{"
                + ",".join(map(cpacket, packets))
                + "};\nstatic const packet_t fixture_checks[]={"
                + ",".join(map(cpacket, checks))
                + "};\n"
            )
            binary = folder / "retained-state"
            build = subprocess.run(
                [
                    shutil.which("cc"),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-ffunction-sections",
                    "-fdata-sections",
                    "-I",
                    str(ROOT / "tests/firmware_stubs"),
                    "-I",
                    str(folder),
                    str(ROOT / "tests/player_retained.c"),
                    str(ROOT / "firmware-source/main/wire.c"),
                    "-Wl,--gc-sections",
                    "-lm",
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 6, run.stdout)
