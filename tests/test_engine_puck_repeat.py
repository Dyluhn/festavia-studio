import unittest
import protocol  # noqa: F401 -- installs aliases for the shipped protocol modules
from player import compile_scene, fit_scene, scattered_index, recovery_plan, color
from hue_mesh import pack_xy


class PuckRepeatTests(unittest.TestCase):
    def test_all_effects_are_bounded_and_never_send_power_commands(self):
        from player import PUCK_EFFECTS

        for n, speed in ((n, speed) for n in (1, 2, 3, 4, 9) for speed in (0.1, 1, 20)):
            for effect in PUCK_EFFECTS:
                for reverse in (False, True):
                    samples, fps = compile_scene(
                        self.scene(n, effect=effect, reverse=reverse, speed=speed), []
                    )
                    self.assertLessEqual(len(samples), 64)
                    self.assertLessEqual(fps, 10)
                    for sample in samples:
                        data = bytes.fromhex(sample)
                        self.assertFalse(data[0] & 1, (n, effect))
                        self.assertTrue(1 <= data[2] <= 25, (n, effect, data[2]))

    def test_new_effects_have_distinct_meaningful_motion(self):
        from player import PUCK_EFFECTS

        banks = {effect: compile_scene(self.scene(effect=effect), [])[0] for effect in PUCK_EFFECTS}
        self.assertEqual(len({tuple(bank) for bank in banks.values()}), len(PUCK_EFFECTS))
        self.assertEqual(banks["bounce"][5], banks["bounce"][-5])
        for frame in banks["color_fade"]:
            data = bytes.fromhex(frame)
            self.assertEqual(len({data[i : i + 3] for i in range(10, 22, 3)}), 1)
        allowed = {pack_xy(*color(c)) for c in self.scene()["colors"]}
        for frame in banks["chase"]:
            data = bytes.fromhex(frame)
            self.assertEqual(data[3:5], b"\0\0")
            self.assertTrue(all(data[i : i + 3] in allowed for i in range(10, 22, 3)))
        levels = [bytes.fromhex(frame)[2] for frame in banks["heartbeat"]]
        peaks = [
            i
            for i in range(1, len(levels) - 1)
            if levels[i] > levels[i - 1] and levels[i] > levels[i + 1]
        ]
        self.assertEqual(len(peaks), 2)

    def test_owner_reuses_tls_between_commands_and_closes_it_explicitly(self):
        from unittest.mock import Mock
        from player import Player

        p = Player.__new__(Player)
        p.http = Mock()
        p.http.call.return_value = {"ok": True}
        p.status()
        p.status()
        p.http.close.assert_not_called()
        p.close()
        p.http.close.assert_called_once()

    def test_failed_setup_reports_verified_recovery_without_waiting_a_full_minute(self):
        from player import Player

        p = Player.__new__(Player)
        p.status = lambda: dict(state="restored", reason="setup_failed")
        with self.assertRaisesRegex(RuntimeError, "setup_failed"):
            p.wait({"armed"}, 60)

    def scene(self, n=4, **fields):
        colors = [
            "#ff0000",
            "#00ff00",
            "#0000ff",
            "#ff00ff",
            "#ffff00",
            "#00ffff",
            "#ffffff",
            "#ff8000",
            "#8000ff",
        ][:n]
        return fit_scene(
            dict(dict(layout_mode="pucks", effect="static", colors=colors, brightness=10), **fields)
        )

    def test_compensation_renders_the_chosen_order_at_every_logical_puck(self):
        for n in range(1, 10):
            for reverse in [False, True]:
                with self.subTest(n=n, reverse=reverse):
                    scene = self.scene(n, reverse=reverse)
                    samples, _ = compile_scene(scene, [])
                    data = bytes.fromhex(samples[0])
                    self.assertEqual(len(scene["layout"]), 27)
                    self.assertEqual(len(data), 12 + 3 * max(2, n))
                    self.assertEqual(data[:3], b"\x52\x01\x19")
                    self.assertEqual(data[3:5], b"\x04\x00")  # Measured 400 ms native default.
                    self.assertEqual(data[-2:], b"\xd8\x00")
                    for puck in range(27):
                        slot = scattered_index(puck % n, n)
                        selected = (26 - puck) % n if reverse else puck % n
                        self.assertEqual(
                            data[10 + 3 * slot : 13 + 3 * slot],
                            pack_xy(*color(scene["colors"][selected])),
                        )

    def test_flow_moves_the_palette_by_one_puck_without_changing_native_offset(self):
        scene = self.scene(effect="flow", fps=4, speed=1)
        samples, _ = compile_scene(scene, [])
        self.assertEqual(len(samples), 16)
        data = bytes.fromhex(samples[4])
        for puck in range(27):
            slot = scattered_index(puck % 4, 4)
            self.assertEqual(
                data[10 + 3 * slot : 13 + 3 * slot],
                pack_xy(*color(scene["colors"][(puck - 1) % 4])),
            )
        self.assertTrue(all(bytes.fromhex(s)[-1] == 0 for s in samples))

    def test_unsupported_counts_and_independent_tones_are_rejected_before_hardware(self):
        s = self.scene()
        for colors in [s["colors"] * 7, ["#ff0000", "#001100"]]:
            with self.subTest(colors=colors), self.assertRaises(ValueError):
                compile_scene({**s, "colors": colors}, [])
        with self.assertRaisesRegex(ValueError, "per-puck fps"):
            compile_scene({**s, "effect": "flow", "fps": 20}, [])

    def test_off_recovery_and_startup_never_light_the_stored_high_level(self):
        before = {
            "on": False,
            "level": 115,
            "color": {"3": 11140, "4": 45873, "7": 370, "8": 2},
            "segments": [[0, 27]],
            "logical_count": 27,
            "aliases": [100],
        }
        device = type("Device", (), {"identity": {}, "endpoint": 11, "address": 0xBF31})()
        plan = recovery_plan(
            {"ieee": "0017880100000001", "extpan": "0123456789abcdef"},
            device,
            before,
            before["segments"],
            before["aliases"],
            startup_level=25,
            native=True,
        )
        self.assertEqual(plan["address"], 0xBF31)
        self.assertEqual(plan["ieee"], "0017880100000001")
        on, level = False, 115

        def apply(packets):
            nonlocal on, level
            for p in packets:
                payload = bytes.fromhex(p["payload"])
                if p["cluster"] == 6:
                    on = bool(p["command"])
                if p["cluster"] == 8 and (on or len(payload) >= 5 and payload[-2:] == b"\x01\x01"):
                    level = payload[0]
                self.assertFalse(
                    on and level >= 51, "A stored brightness above the test ceiling became visible"
                )

        apply(plan["setup"])
        self.assertTrue(on)
        self.assertEqual(level, 25)
        apply(plan["restore"])
        self.assertFalse(on)
        self.assertEqual(level, 115)

    def test_on_snapshot_still_recovers_color_and_level_after_an_external_off(self):
        before = {
            "on": True,
            "level": 25,
            "color": {"3": 11140, "4": 45873, "7": 370, "8": 2},
            "segments": [[0, 27]],
            "logical_count": 27,
            "aliases": [100],
        }
        device = type("Device", (), {"identity": {}, "endpoint": 11})()
        plan = recovery_plan(
            {"ieee": "0017880100000001", "extpan": "0123456789abcdef"},
            device,
            before,
            before["segments"],
            before["aliases"],
            startup_level=25,
            native=True,
        )
        for packet in plan["restore"]:
            if packet["cluster"] in (8, 0x300):
                self.assertEqual(bytes.fromhex(packet["payload"])[-2:], b"\x01\x01")


if __name__ == "__main__":
    unittest.main()
