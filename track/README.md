# Festavia Track

A customizable, modular soffit track for **Philips Hue Festavia permanent outdoor
puck lights**. Plan a straight run, print numbered sections, lock the joints with
replaceable splice bars and pins, then lift the run into sliding-lever brackets.

This is a mechanical mounting kit. It does not need an ESP32, Home Assistant or
a Hue integration. Independent community design; not affiliated with Signify.

![A completed straight track with the Festavia pucks illuminating the siding](assets/installed-run.jpg)

## Start here

**[Customize on MakerWorld](https://makerworld.com/en/models/3665672-festavia-track-modular-soffit-mount-for-hue)** · **[Download the complete track kit](https://raw.githubusercontent.com/Dyluhn/festavia-studio/track-downloads/v0.1.1/Festavia-MakerWorld.zip)**. Extract the ZIP and open `workbench/index.html` in your browser, or use the three SCAD files in MakerWorld.

1. [Configure your track (PDF)](docs/Festavia-Configuration-Guide.pdf) · [Phone/browser edition](docs/Festavia-Configuration-Guide.html). Measure your run, set puck spacing and bracket positions, then check and export the plates in MakerWorld.
2. [Assemble your track (PDF)](docs/Festavia-Assembly-Manual.pdf) · [Phone/browser edition](docs/Festavia-Assembly-Manual.html). Follow the illustrated puck, joint, bracket and cable-routing sequence for your own layout.
3. [Optional boxes and cable clips](accessories/README.md). Choose the cable slack box, the power-supply cradle or just the clips. The offline workbench includes all seven parts under **Boxes & clips**.

**Bambu users** can edit dimensions and generate printable plates online. Open the [MakerWorld guide and SCAD files](makerworld/README.md) for a single section, fit tests or a whole run. The workbench’s **Save MakerWorld model** button carries your current measurements into the online editor.

Open the [offline HTML workbench](workbench/index.html) and choose **Design a section** to change its length, ends, holder and receiver positions, shell thickness and joint fit. **Design a run** recalculates puck positions, brackets, joints, sections and packed plates from your measurements. Both views generate STL geometry on your device using the release OpenSCAD model. Save a section as editable SCAD or a run as a JSON configuration for the whole-kit exporter. **Explore examples** opens the five reference layouts and the community ZIP verifier.

1. Read [Getting started](docs/GETTING_STARTED.md).
2. Print the small [fit-first kit](docs/ASSEMBLY.md#fit-first) with your intended
   material and settings before making a complete run.
3. Customize `festavia_track.scad` in OpenSCAD, or open the **Make Track** launcher
   for your computer to export a complete kit. The launcher uses Python 3.12+ and
   OpenSCAD. It prepares its own geometry-tool environment on the first build.
4. Follow your generated `layout.svg`, `cut-list.csv` and `assembly.csv`.

[Reference build and print settings (PDF)](docs/Festavia-Track-Guide.pdf)

The [desktop example archive](https://raw.githubusercontent.com/Dyluhn/festavia-studio/track-downloads/v0.1.1/festavia-track-0.1.0-community-beta.zip) includes ready-to-slice STL and geometry-only 3MF examples for
180 mm and 256 mm beds. The 3MF files contain individually named components;
they contain **no printer-specific G-code or machine profile**. Slice them for
your own printer. Use either packed plates or individual parts, not both.

## What you can change

| Setting | Supported customization |
|---|---|
| Run length | 12–600 in / 304.8–15,240 mm per separately supported straight run |
| Light spacing | 12–21 in / 304.8–533.4 mm; excess factory cable stays loose in the channel |
| Placement | Automatic centered layout, or a measured first-light offset |
| Existing mounting holes | Optional exact bracket centres in mm; clearance/span rules still apply |
| Printer bed | 180–400 mm on each axis, including rectangular beds; no diagonal placement |
| Shell | Installed reference, full 3.2 mm reinforced shell, or custom 1.6–3.2 mm face / 1.8–3.2 mm side walls |
| Fit | A0 reference joints, or ±0.05 mm joint-fit variants for calibration |
| Printing | Single-nozzle breakaway supports, or original dual-material interface geometry |
| Ends and cable | Wire or blank gates; flat-wire and round-cord clips |

There is no hard-coded pack quantity. Light count follows run length, spacing and
end margins. For example, a 600 in run at 12 in spacing can plan 50 holders.
The software's geometry count does not authorize electrically extending a light
string: follow the light manufacturer's limits and installation instructions.

### The established joints, with optional extra reinforcement

The default retains the installed **A0 train-track joint**: two tongues, two splice
bars and two barbed cross pins per seam. The reinforced holder supports the lock
tabs that broke in the early design. Rings turn 20° and are secured by stop pins.

![Exploded A0 joint](assets/03_joint_exploded.png)

An optional full-shell profile increases the measured plain-section vertical
second moment of area by **68%**, with **79% more material area in that section**.
The comparison uses the cross section of the exported track. [Structure and material details](docs/STRUCTURE.md).

## Export a kit

From a clone of Festavia Studio, open the `track` directory before running the commands below.

With Python 3.12+ and OpenSCAD installed:

```sh
python make_track.py --config examples/garage-256.json --output my-track-output
```

On macOS/Linux the Python command may be `python3`. Or double-click the platform
launcher and answer its measurement prompts. To generate only the plan, add
`--plan-only`; this needs no third-party Python packages.

Your output contains:

- Numbered track STLs / 3MFs, one hardware model per type, and fit-first coupons.
- Packed plates, with their required quantities and small-part spares included.
- A cut list, hardware BOM, bracket/light layout, and per-joint pin directions.
- The exact saved configuration, model fingerprint, mesh checks and file hashes.

See [Customization](docs/GETTING_STARTED.md#customize-your-run) for OpenSCAD
Customizer presets, measured bracket positions and multi-run installations.

## Check your puck

The holder fits the Festavia permanent outdoor puck with a roughly 35 mm body
and 49 × 20 mm mounting tabs. Match that shape before printing. Festavia fairy
lights and globe strings use different mounts.

[Assembly](docs/ASSEMBLY.md) · [Validation](docs/VALIDATION.md) ·
[Design audit](docs/DESIGN_AUDIT.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
