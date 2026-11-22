"""Check MakerWorld entry points with the same module isolation as an SCAD importer."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from makerworld.build import ROOT, model


class MakerWorldTests(unittest.TestCase):
    def test_upload_files_match_source(self):
        source = (ROOT / "festavia_track.scad").read_text()
        for mode in ("section", "run"):
            path = ROOT / "makerworld" / f"Festavia-{mode.title()}.scad"
            self.assertEqual(model(source, mode), path.read_text())

    def run_batch(self, batch, bed=256, size=4):
        with tempfile.TemporaryDirectory() as path:
            src = Path(path) / "batch.scad"
            model_file = ROOT / "makerworld" / "Festavia-Run.scad"
            calls = "\n".join(f"mw_plate_{slot}();" for slot in range(1, 17))
            src.write_text(f"use <{model_file}>\n{calls}\n")
            out = src.with_suffix(".echo")
            subprocess.run(
                [
                    "openscad",
                    "-o",
                    str(out),
                    "-D",
                    "run_length=3048",
                    "-D",
                    f"batch_number={batch}",
                    "-D",
                    f"plates_per_file={size}",
                    "-D",
                    f"bed_x={bed}",
                    str(src),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            return out.read_text()

    def test_batch_mapping_and_hidden_guards(self):
        self.assertEqual(self.run_batch(1, size=16).count("PLATE_PARTS"), 9)
        first = self.run_batch(1)
        last = self.run_batch(3)
        self.assertEqual(first.count("PLATE_PARTS"), 4)
        self.assertEqual(last.count("PLATE_PARTS"), 1)
        self.assertNotIn("WARNING", first + last)
        self.assertNotIn("ERROR", first + last)
        self.assertIn("Batch number must be a whole number", self.run_batch(4))
        self.assertIn("bed dimensions must be 180 to 400 mm", self.run_batch(1, 415))
