"""Exercise actual plans, deliberate bad plans, and file interchange."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import trackkit


class ConfigTests(unittest.TestCase):
    def config(self, **changes):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(
                json.dumps({"schema_version": 1, "name": "test", "parameters": changes})
            )
            return trackkit.load_config(path)

    def test_units_and_range_limits(self):
        self.config(
            length_unit="mm",
            run_length=5000,
            light_spacing=400,
            light_margin_min=100,
            bracket_spacing_max=600,
            bracket_end_max=200,
        )
        for params in [
            {"run_length": 601},
            {"bed_x": 179},
            {"light_spacing": 22},
            {"support_gap": 0.1},
            {"side_wall": 3.4},
            {"face_skin": 1.2},
            {"clips_flat": 1.5},
            {"single_nozzle": "false"},
            {"run_length": True},
            {"run_length": float("nan")},
            {"fit_profile": "oops"},
            {"run_lenght": 100},
        ]:
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.config(**params)

    def test_no_machine_execution_or_path_fields_in_config(self):
        for params in [
            {"part": "include <other.scad>"},
            {"output": "../somewhere"},
            {"machine_start_gcode": "G28"},
        ]:
            with self.assertRaises(ValueError):
                self.config(**params)

    def test_launcher_help_does_not_bootstrap(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "make_track.py"), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.command, _ = trackkit.openscad_command()
        cls.config = trackkit.load_config(ROOT / "examples/garage-256.json")
        cls.baseline = trackkit.plan(cls.config, cls.command)

    def test_installed_reference_plan(self):
        p = self.baseline
        self.assertEqual(
            (
                len(p["lights_mm"]),
                len(p["pieces"]),
                len(p["brackets_mm"]),
                p["plate_count"],
            ),
            (11, 27, 8, 12),
        )
        for a, b in zip(p["lights_mm"], [254 + 406.4 * i for i in range(11)]):
            self.assertAlmostEqual(a, b, places=3)
        for a, b in zip(p["brackets_mm"], [152.4 + 609.6 * i for i in range(8)]):
            self.assertAlmostEqual(a, b, places=3)

    def test_all_example_presets_keep_every_light(self):
        for path in (ROOT / "examples").glob("*.json"):
            with self.subTest(example=path.name):
                trackkit.plan(trackkit.load_config(path), self.command)

    def test_corrupt_plans_fail_independent_checks(self):
        mutations = [
            lambda p: p["lights_mm"].pop(),
            lambda p: p["brackets_mm"].__setitem__(1, p["brackets_mm"][0] + 700),
            lambda p: p["joints_mm"].__setitem__(0, p["lights_mm"][0]),
            lambda p: p["pieces"][0].__setitem__("length_mm", 999),
            lambda p: p["pieces"][1]["light_offsets_mm"].__setitem__(0, 0),
            lambda p: p["hardware"][0].__setitem__("required", 0),
            lambda p: p["track_plates"][0][0].append(0),
            lambda p: p["hardware_placements"].pop(),
            lambda p: p["pin_sides"].pop(),
        ]
        for mutate in mutations:
            p = copy.deepcopy(self.baseline)
            mutate(p)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                trackkit.validate_plan(p)

    def test_180_bed_keeps_eight_lights(self):
        p = trackkit.plan(
            trackkit.load_config(ROOT / "examples/small-bed-180.json"), self.command
        )
        self.assertEqual(len(p["lights_mm"]), 8)
        self.assertLessEqual(max(s["length_mm"] for s in p["pieces"]), 164.01)

    def test_measured_first_light_and_brackets_are_preserved(self):
        c = copy.deepcopy(self.config)
        c["parameters"].update(
            light_placement="fixed",
            first_light_offset=10,
            bracket_centres_mm=",".join(str(x) for x in self.baseline["brackets_mm"]),
        )
        p = trackkit.plan(c, self.command)
        self.assertEqual(p["lights_mm"], self.baseline["lights_mm"])
        self.assertEqual(p["brackets_mm"], self.baseline["brackets_mm"])
        for mutate in [
            lambda p: p["lights_mm"].__setitem__(0, 260),
            lambda p: p["brackets_mm"].__setitem__(0, 160),
        ]:
            bad = copy.deepcopy(p)
            mutate(bad)
            with self.assertRaises(ValueError):
                trackkit.validate_plan(bad)

    def test_incompatible_measured_holes_are_refused(self):
        c = copy.deepcopy(self.config)
        c["parameters"]["bracket_centres_mm"] = (
            "254,762,1371.6,1981.2,2590.8,3200.4,3810,4419.6"
        )
        with self.assertRaises(ValueError):
            trackkit.plan(c, self.command)

    def test_raw_openscad_rejects_invalid_inputs(self):
        # Check the SCAD's own guards, not just the Python schema.
        with tempfile.TemporaryDirectory() as folder:
            for key, value in [
                ("bed_x", 150),
                ("run_length", 9999),
                ("light_spacing", 22),
                ("face_skin", 1.2),
            ]:
                params = self.config["parameters"] | {key: value}
                if key == "face_skin":
                    params["structure_profile"] = "custom"
                out = Path(folder) / (key + ".echo")
                with self.assertRaisesRegex(ValueError, "ERROR:"):
                    trackkit.invoke(self.command, params, "plan", out)

    def test_exact_inch_boundaries_survive_mm_conversion(self):
        # Render a custom part so layout feasibility is separate from numeric
        # input validity. 12 * 25.4 is slightly below literal 304.8 in OpenSCAD.
        with tempfile.TemporaryDirectory() as folder:
            trackkit.invoke(
                self.command,
                self.config["parameters"]
                | {"run_length": 12, "bracket_spacing_max": 8},
                "custom_piece",
                Path(folder) / "boundary.stl",
            )

    def test_zero_spare_percent_disables_spares(self):
        c = copy.deepcopy(self.config)
        c["parameters"]["spare_percent"] = 0
        p = trackkit.plan(c, self.command)
        self.assertTrue(all(h["spares"] == 0 for h in p["hardware"]))

    def test_support_recommendations_follow_the_actual_track_variant(self):
        p = copy.deepcopy(self.baseline)
        for piece in p["pieces"]:
            name = f"track-{piece['number']:03d}"
            self.assertEqual(trackkit.component_supports(name, p), "off")
        p["parameters"]["single_nozzle"] = False
        for piece in p["pieces"]:
            name = f"track-{piece['number']:03d}"
            required = bool(piece["light_offsets_mm"] or piece["bracket_offsets_mm"])
            self.assertEqual(trackkit.component_supports(name, p) != "off", required)
        self.assertNotEqual(trackkit.component_supports("bracket-1", p), "off")
        self.assertEqual(trackkit.component_supports("holder-test", p), "off")


if __name__ == "__main__":
    unittest.main()
