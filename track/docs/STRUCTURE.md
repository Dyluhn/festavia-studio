# Structure, materials and fit

## What changed after the early builds

The early joint system allowed visible sag. Garage kit v2 replaced it with the
installed A0 tongue/socket joint, two press-in splice bars and two barbed cross
pins per seam. Earlier ring-lock tabs broke; the revised holder fills underneath
the tabs and ties the posts into the side walls. Those revised interfaces are the
reference for this kit, not the earlier butterfly-key joint.

The community model keeps the same 56 × 28 mm envelope, light bore, lock path,
receiver, bracket and lever. Optional shell changes fill material only in the
lightened channel areas; they do not deliberately loosen or resize the interfaces.

## Shell profiles

The values below come from a section through the **actual exported mesh**, at
x=30 mm in a plain reference section. `tools/strength_report.py` reproduces them.

| Profile | Face / wall | Area relative to reference | Vertical bending I | Lateral bending I |
|---|---|---|---|---|
| Installed reference | 1.6 / 1.8 mm lightened regions | 1.000× | 1.000× | 1.000× |
| Custom example | 2.4 / 2.4 mm | 1.367× | 1.318× | 1.292× |
| Reinforced | 3.2 / 3.2 mm | 1.787× | 1.684× | 1.639× |

The thicker shell adds material to the plain channel section, increasing its
local bending rigidity for the same material. It also adds weight. Use the bracket
spacing shown in your plan for all three profiles. The installed track uses the
reference shell. Check a joint coupon if you change the shell or filament.

## Material and print orientation

The established fit used PETG. Prusa describes PETG as suitable for indoor and
outdoor mechanical parts; its [PETG guide](https://help.prusa3d.com/article/petg_2059)
also covers bed adhesion and printing limitations. For substantial direct sun,
ASA is an option to investigate because of its UV and temperature resistance,
as described in [Prusa's ASA guide](https://help.prusa3d.com/article/asa_1809).
When changing filament, print the coupons to check shrinkage and fit.

Do not use PLA as the outdoor structural material for this kit. PLA appears in
the old dual-nozzle process only as a removable support-contact interface.
Keep the supplied orientation of bars, pins, brackets and levers; their flexing
features and layer directions matter.

Thermal expansion, retained heat under a soffit, local sun, backing and fasteners
remain installation-specific. The software's maximum length is a planning bound,
not proof that a 15 m rigid run is suitable for every climate. Longer or different
exposures need physical assessment and appropriately separated supported runs.

## What the fit settings do

A0 reproduces the installed joint interfaces. A− and A+ change the joint's crush
rib interference and pin tunnel by ±0.05 mm. The signs describe looser/tighter
behavior; string-valued menu choices avoid relying on negative-valued browser
Customizer presets.

The puck bore and bayonet remain fixed to the measured permanent-light hardware.
They are not a generic adjustable holder for all products sold under the Festavia
name. Measure your puck and test its ring retention before printing a run.
