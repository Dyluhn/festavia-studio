"""Verify the standalone accessory upload and its MakerWorld plate entry point."""

import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
import trimesh

from makerworld.build_accessories import PARTS, ROOT, model


class AccessoryTests(unittest.TestCase):
    def test_standalone_upload_matches_print_parts(self):
        upload = ROOT / "makerworld" / "Festavia-Accessories.scad"
        self.assertEqual(upload.read_text(), model())
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            wrapper = work / "plate.scad"
            wrapper.write_text(f"use <{upload}>\nmw_plate_1();\n")
            for key in PARTS:
                with self.subTest(component=key):
                    copies = 3 if key == "flat-clip" else 1
                    out = work / (key + ".stl")
                    args = ["openscad", "--export-format", "binstl", "-o", str(out),
                            "-D", f'component="{key}"', "-D", f"small_part_copies={copies}", str(wrapper)]
                    subprocess.run(args, check=True, capture_output=True, timeout=60)
                    ref = trimesh.load_mesh(ROOT / "accessories" / "parts" / (key + ".stl"))
                    mesh = trimesh.load_mesh(out)
                    bodies = mesh.split(only_watertight=False)
                    self.assertEqual(len(bodies), copies)
                    for part in bodies:
                        self.assertTrue(part.is_volume)
                        self.assertTrue(np.allclose(sorted(part.extents), sorted(ref.extents), atol=0.001))
                        self.assertAlmostEqual(part.volume / ref.volume, 1, places=4)
