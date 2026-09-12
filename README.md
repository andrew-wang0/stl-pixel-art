# STL Pixel Art

Convert an indexed PNG from GIMP into one aligned STL per used palette index and a solid backing plate. Pixel boundaries stay exact: no resampling, antialiasing, or color quantization. This program generates geometry, never printer G-code.

## Install and run

Requires Python 3.10 or later.

```sh
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
stl-pixel-art pixelart.png --output-dir pixel_stls
```

You can also run `python pixel_art.py pixelart.png` after installation.

```sh
stl-pixel-art pixelart.png --pixel-mm 0.30 --color-height 0.10 --total-height 1.00 -o pixel_stls
python -m unittest discover -s tests -v
```

In GIMP, convert the image to **Indexed** mode and export as a lossless PNG. Each used palette index becomes a separate part, even when two indices have identical RGB values. Transparent pixels are rejected: flatten the image first so invisible pixels do not unexpectedly become plastic. Unused palette entries are ignored. Indexed PNG supports up to 256 entries; the software does not assume that your available filament slots cover every color.

The output directory must be new or empty. Use a new directory for each conversion to avoid mixing stale parts. Output includes:

```text
color_00_000_000_000.stl
color_01_255_000_000.stl
...
backing.stl
palette.json
```

Filenames encode palette index and RGB, not automatic filament assignments. The JSON manifest records dimensions, colors, pixel counts, and filenames. STL has no reliable color or unit metadata; all coordinates here are in millimeters.

## Geometry and orientation

At the defaults, each pixel occupies 0.30 × 0.30 mm. Color parts occupy Z=0–0.10 mm, and the backing occupies Z=0.10–1.00 mm. A 200 × 200 image produces an 60 × 60 mm model. Every part uses the same origin; no mesh is independently centered.

The PNG rows are flipped vertically before extrusion: the bottom PNG row occupies Y=0–0.30 mm and X increases to the right. The artwork is recognizable from above (+Z). Because the intended visible surface is the underside, viewing the finished print from below reverses handedness. For readable text on that face, horizontally mirror the input in GIMP before conversion.

Top and bottom faces follow the pixel grid. Side faces exist only on color boundaries, including hole boundaries. Adjacent same-color pixels share vertices and have no internal walls; the program does not create a separate cube object per pixel. It validates closed surfaces, consistent winding, and positive volume before export.

Diagonal pixels touch along a vertical edge. They use separate topological vertices to remain closed shells, preserving the exact artwork. STL stores triangle coordinates only; software that welds coincident vertices may report these edge contacts as non-manifold. Inspect such patterns in the slicer, or edit the source to separate or connect those pixels with an edge if needed. No geometric repair that changes pixels is applied. Runtime and mesh size scale with pixel count; rectangle merging and 3MF export are future improvements.

## Bambu Studio workflow

1. Select **all generated STL files together**, including `backing.stl`.
2. Load them as **one object with multiple parts**, retaining their relative coordinates.
3. Assign each color part to its matching filament/AMS slot and choose a backing filament.
4. Select your P1S with the 0.2 mm nozzle profile and keep the colored face at Z=0 on the build plate.
5. Configure first-layer/layer heights so a layer boundary coincides with the color thickness. The default 0.10 mm is a geometry starting point, not a guarantee that your current profile uses that first-layer height. Adjust the geometry or slicer settings together.
6. Slice and inspect Preview, especially the first layer, thin pixel features, color boundaries, and transition to backing. Verify the finished dimensions and that only the bottom layer(s) use the artwork colors.

Bambu Studio handles temperatures, extrusion, AMS swaps, and machine G-code. Actual slicer import and a physical print must be verified on your setup; automated tests check mesh geometry and STL round trips.
