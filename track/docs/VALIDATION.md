# Digital validation — 0.1.0

## Optional accessory verification · 22 November 2026

All seven supplied STLs were single watertight solids with consistent winding. Native OpenSCAD rendered all seven selector options at their original dimensions. Fourteen geometry, copy-count and bed checks covered the 180 mm limit, rotated rectangular placement, and rejection of oversized parts or groups. The standalone phone-sized workbench previewed all seven, exported a four-clip STL and editable SCAD, and recovered after an invalid bed selection. MakerWorld rendered the cable storage base and the revised power-supply cover from the same complete accessory file.

Bambu Studio 2.9.1.70 produced G-code and reported a successful slice for every accessory using the archived X2D PETG settings. Its log reproduced tool-command diagnostics from the original profile and a fill diagnostic on the PSU cover. The download contains geometry for builders to slice under their own printer settings. Verification used no new physical prints, load tests or thermal tests.


The November 18 Linux tests below compare the community model with the installed PETG track.

The release model SHA-256 is
`2361cb69bc1c149056a19309aff5536abde3f6d940a3f4dc7dffc775593db3d2`.
Machine-readable results are in [validation-summary.json](validation-summary.json).

## What passed

| Check | Evidence and coverage |
|---|---|
| Regression tests | 13 tests: schema/ranges, safe parameters, all example plans, default positions, measured-position preservation, intentional plan corruption, invalid raw SCAD inputs, launcher help, exact inch/mm boundaries, zero spares and support recommendations for both track variants |
| Dense layout sweep | 1,100 layouts: four bed sizes, 24–240 in lengths in 4 in steps, five light spacings from 12 to 21 in; independent checks of features, clearances, section lengths, caps, BOM and plate coverage |
| Long-run boundary matrix | 96 layouts including 300 in and 600 in runs; 180, 220, 256 and 350 × 320 mm beds |
| Extra boundaries | 30 cases covering rotated/400 mm beds and 12, 16, 20, 599 and 600 in lengths; 24 valid layouts and six correctly refused 12 in layouts whose mechanisms cannot fit |
| Complete exports | Nine kits, 426 STL models and 426 matching geometry 3MF files; five public examples, three saved-coordinate house plans and a rotated-bed/custom-shell/cable-clip case |
| Mesh integrity | Closed, consistently wound, positive-volume meshes; float32 manifold checks, exact connected-body counts, plate bounds, component separation and 3MF round-trip bounds/volume |
| Reference preservation | 19 part comparisons against the November 11 reference model, with zero symmetric difference and zero bounding-box delta for the installed shell with original support geometry |
| Original printed-design references | The prior model's 20-case oracle check passes its documented tolerances; this is a CAD comparison to saved manufacturing geometry, not a new physical fit test |
| Motion and retention | 175 swept positions for lever travel, lift, ring turn and drop; no unintended collisions. Intended latch/stop contacts engage. Reinforced shell checked as well as the reference |
| Test sensitivity | Intentionally reducing the bore to 34.6 mm fails the puck-clearance check, as required |
| Fit variants | Nine shell/joint-fit combinations plus the 0.2 and 0.5 mm support-gap boundaries export as closed solids with the expected body counts |
| Slicing | All 12 default 256 mm plates, both fit plates, and all 15 small-bed plates: 29 successful slicer results. Final released 3MF bytes match the sliced inputs exactly |
| Section properties | Exported-mesh sections reproduce the area and bending-I comparisons in [Structure](STRUCTURE.md); these are geometric properties, not a structural qualification |

Full default run builds use OpenSCAD 2026.11.06's manifold backend. The portable
runner also detects OpenSCAD 2021.01 and uses its CGAL backend. The 2021.01
compatibility run covered the 19 reference parts, the two coupon plates and
the three measured-position plans. That run preceded the final numeric-boundary
tolerance, zero-spare and print-list corrections; it used the same part geometry.
The main complete-kit
and layout results above use the final model fingerprint.

The single-nozzle tests allow the explicitly identified small bridges; CAD cannot
measure filament sag or how easily the ribs snap out. An unchanged interference
in an artificial axial ring-drop pose is recorded as reference information; the
intended 20° turn-and-drop path is the path checked for assembly clearance.

## Slicer setup and limits

Bambu Studio 2.9.1 was run locally through its CLI. Reference settings were PETG,
0.4 mm nozzle, 0.28 mm layers, two walls and 10% infill. Tree supports were enabled
for bracket/lever plates; track and other hardware plates used supports off.
No print jobs were sent.

The 256 mm tests used the saved X2D reference profiles. The 180 mm tests used
the same profile with its printable XY boundary reduced to 180 × 180 mm: this
checks plate/toolpath geometry, **not qualification of an A1 mini or every
180 mm printer profile**. Slicer compatibility-name failures during creation of
that synthetic profile were setup errors and were corrected before the reported
29 successful results. Original 4 mm hardware spacing also produced a real
tree-support collision. The released packing uses separate supported-hardware
plates and a 10 mm halo per bracket/lever; the corrected full plates pass.

Slicer results are not a prediction of identical material use, time or fit on
another machine. Public 3MFs contain geometry and component names only. Printer
profiles, local sliced projects and G-code are excluded from the distribution.

## Portability and packaging

The core exporter and all nine builds ran in a fresh Python 3.12 environment
installed from `requirements.txt`. The plan-only path uses the standard library.
Runtime packages, developer-only tools and PDF-authoring dependencies are split.
The distribution contains explicit public source inputs and five verified example
kits, a file-hash inventory and a CRC-checked ZIP. Extracted-kit checks cover file
hashes, example meshes, the Linux launcher and saved-config planning in a path
containing spaces. Windows/macOS launchers are supplied but were not executed on
those operating systems here. See the online export results below.

## Physical checks still required for a printer/installation

Use [Fit first](ASSEMBLY.md#fit-first) and [FIT_REPORT.json](FIT_REPORT.json).
Check rib release, actual puck/ring retention, bar/pin fit, lever travel/latching,
cable routing and repeat assembly with the intended filament and settings.
Alternative materials/shells, UV exposure, thermal creep, wind, backing,
fasteners and service life have no new measured qualification in this release.
The supplied software length range is not an outdoor load rating.

Reproduce public checks using [Contributing](../CONTRIBUTING.md). Old private
installation files and oracle folders are not required to customize a track.

## MakerWorld online export

The signed-in Parametric Model Maker generated a resized 207.5 mm section and a complete 4,572 mm run on November 22, 2026. The P1S run downloaded as a single 12-plate project. Bambu Studio 2.9.1.70 sliced all 12 plates and returned success for the project. Its per-plate warning fields were empty. The CLI log included concentric-infill diagnostics. The project opened with the default PLA profile and supports disabled. For the reference PETG build, the bracket and lever plates (8 and 9) require tree supports. All 12 meshes were watertight, had the expected number of separate bodies, and matched the reference packed dimensions within 0.001 mm. In four-plate mode, a 3,048 mm run showed a single populated slot in its final batch.
