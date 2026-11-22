# Audit and completed work — November 18, 2026

## Latest baseline recovered

The latest track-specific design was the November 11 OpenSCAD customizer, after
the October garage kit v2 and sag-fix work. Its A0 joints and revised holder were
ported from the printed installation and had extensive CAD comparisons. The owner
reported no additional known failures with those newer parts on November 18.

The older customizer and installation sources are preserved. This community
directory is the self-contained distribution candidate.

## Gaps and disposition

| Gap in the earlier work | Completed disposition |
|---|---|
| No complete community distribution | Source, launchers, editable presets, STLs, geometry 3MFs, examples, guides and hashes packaged together |
| Tools depended on local account paths and private oracle folders | Portable exporter and public validation commands use paths relative to the extracted kit; prior-model comparison is optional maintainer input |
| Manual one-at-a-time exports | One command makes the whole kit, BOM, cut list, diagram, pin schedule and named plates |
| No small end-to-end joint-fit plate | Added two mating short ends, two bars and two pins on a plate that fits a 180 mm bed |
| Negative-valued public fit/default offset controls could be fragile in cloud Customizers | Named fit choices and explicit left/right offset selectors; nonnegative visible defaults |
| No optional stronger shell | Added full 3.2 mm and bounded custom shells; measured section properties, retained reference interfaces |
| Metric preset could generate a 34.3 mm cap-end piece | Corrected minimum cap-end length to 47 mm on every planner path; the earlier cap insert and joint block could otherwise overlap |
| End-piece seam accounting could allow 240.2 mm under a 240 mm limit | Dynamic-programming length guard now uses the actual end-piece length while retaining the installed layout's tie-break objective |
| Planning-only output could miss an invalid-spacing assertion | The same fail-closed layout checks now cover machine-readable planning |
| Exact 12 in / 8 in boundary inputs could fail after floating-point conversion to mm | Added numeric tolerance to input-boundary guards; mechanical clearance rules are unchanged |
| Existing house offsets/holes could not be preserved explicitly | Added fixed first-light offset and exact bracket-centre input, checked against all span and insertion clearances |
| Printable plate components lacked helpful names | Geometry 3MF objects carry part names; bracket/lever support requirements are recorded per component |
| Mesh-valid packed hardware produced colliding organic-support toolpaths | Slicer regression exposed the collision; bracket/lever plates now have a 10 mm per-part support halo and are separated from support-free hardware |
| Source mesh checks alone could miss exported-file defects | Every export is reloaded, checked in float32 and round-tripped through 3MF; body counts, bed bounds and plate separation are checked |
| No independent BOM/plate accounting | Cross-checks ensure every numbered piece appears once, and hardware counts/spares match both the BOM and packed plates |
| No full kit integrity record | Configuration, model hash, tool version, geometry checks, per-file hashes and a completion marker travel with each build |
| The first community track exporter omitted a box that only had a base | The optional accessory model pairs the original cable base with its revised v2 lid and provides the arched supply base and cover, shims and both clips. Accessory plates are selected separately from the run. |

## Deliberate scope and physical qualification

The run planner keeps the established maximum support span and conservative
feature clearances. It is not a global minimum-bracket optimizer; some combinations
use more brackets to fit the mechanisms. Corners use independently supported runs
with cable transitions, not an unqualified structural elbow.

The installed A0 PETG interface is the physical reference. No new parts were sent
to a printer in this development run. Single-nozzle rib release, new printer or
filament fits, alternative shells, repeat-assembly wear and outdoor service life
remain physical observations to collect using the supplied fit report. They are
not reported as passed by CAD or slicer checks.

See [Validation](VALIDATION.md) for the final digital checks and exact boundaries
of the release's evidence.
