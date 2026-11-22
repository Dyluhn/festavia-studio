# Offline parametric workbench

Open index.html directly. **Boxes & clips** previews seven optional accessory components. Choose the bed size, set clip or shim copies, then save the plate STL or a configured MakerWorld file. Design a section edits a single printable part in mm. Design a run plans a complete straight run in the selected units and renders the selected piece, hardware part or packed plate. The STL export contains the geometry currently in the viewer. Use the run JSON with the community exporter for a whole kit. Choose **Save MakerWorld model** to transfer editable measurements into Bambu’s online editor. The run export starts at batch 1. [Online guide](../makerworld/README.md). Invalid geometry disables export and shows the reason from the model.

The HTML includes the v0.1.0 model, sample data, a WebAssembly OpenSCAD runtime, and the Liberation Sans Bold font used to engrave part numbers. Edits run in a cancellable local worker. The installed puck bore and bracket mechanism remain fixed by the source model.

## Rebuild

Download the [original example archive](https://raw.githubusercontent.com/Dyluhn/festavia-studio/track-downloads/v0.1.1/festavia-track-0.1.0-community-beta.zip). From this directory, run:

```sh
npm ci --ignore-scripts
python build.py /path/to/festavia-track-0.1.0-community-beta.zip index.html
```

The build verifies the input archive and runtime fingerprints. It adapts the runtime wrapper's module export and module URL for a classic worker to allow opening from file://. The WASM binary is unchanged. The engine is [openscad-wasm 0.0.4](https://www.npmjs.com/package/openscad-wasm/v/0.0.4), distributed under GPL-2.0; upstream [engine sources and build scripts](https://github.com/openscad/openscad-wasm) and [OpenSCAD source](https://github.com/openscad/openscad). Liberation Sans is distributed under the SIL Open Font License. Both license texts are in vendor/ and embedded in the HTML.
