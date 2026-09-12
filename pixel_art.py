"""Convert exact palette-index pixels into aligned, face-down STL parts."""

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import trimesh


def pixel_mesh(mask, pixel_mm, color_height):
    """Extrude a boolean grid, omitting shared walls and splitting corner contacts.

    At a grid vertex, diagonally opposed filled cells get distinct vertex IDs.
    This keeps each incident surface closed without changing pixel boundaries.
    """
    height, width = mask.shape
    vertices, faces, ids = [], [], {}

    def occupied(x, y):
        return 0 <= x < width and 0 <= y < height and mask[y, x]

    def vertex(x, y, z, cell):
        incident = {(cx, cy) for cx, cy in
                    ((x-1, y-1), (x, y-1), (x-1, y), (x, y))
                    if occupied(cx, cy)}
        group, pending = {cell}, [cell]
        while pending:
            cx, cy = pending.pop()
            for neighbor in ((cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)):
                if neighbor in incident and neighbor not in group:
                    group.add(neighbor)
                    pending.append(neighbor)
        key = (x, y, z, min(group))
        if key not in ids:
            ids[key] = len(vertices)
            vertices.append((x * pixel_mm, y * pixel_mm, z * color_height))
        return ids[key]

    def quad(points, cell):
        a, b, c, d = [vertex(*point, cell) for point in points]
        faces.extend(((a, b, c), (a, c, d)))

    for y, x in zip(*np.nonzero(mask)):
        x, y = int(x), int(y)
        cell = (x, y)
        quad(((x,y,0),(x,y+1,0),(x+1,y+1,0),(x+1,y,0)), cell)
        quad(((x,y,1),(x+1,y,1),(x+1,y+1,1),(x,y+1,1)), cell)
        if not occupied(x, y-1):
            quad(((x,y,0),(x+1,y,0),(x+1,y,1),(x,y,1)), cell)
        if not occupied(x+1, y):
            quad(((x+1,y,0),(x+1,y+1,0),(x+1,y+1,1),(x+1,y,1)), cell)
        if not occupied(x, y+1):
            quad(((x+1,y+1,0),(x,y+1,0),(x,y+1,1),(x+1,y+1,1)), cell)
        if not occupied(x-1, y):
            quad(((x,y+1,0),(x,y,0),(x,y,1),(x,y+1,1)), cell)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    if not len(faces) or not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ValueError("Generated color mesh is not a closed, outward-facing solid")
    return mesh


def alignment_markers(width, height, pixel_mm, slot, slot_count, height_mm):
    """Four disjoint registration pixels giving each part common XY extrema."""
    span_x = max(width, slot_count * pixel_mm)
    span_y = max(height, slot_count * pixel_mm)
    offset = slot * pixel_mm
    boxes = []
    for x, y in ((offset, -2*pixel_mm), (offset, span_y+pixel_mm),
                 (-2*pixel_mm, offset), (span_x+pixel_mm, offset)):
        box = trimesh.creation.box(extents=(pixel_mm, pixel_mm, height_mm))
        box.apply_translation((x+pixel_mm/2, y+pixel_mm/2, height_mm/2))
        boxes.append(box)
    return trimesh.util.concatenate(boxes)


def convert(input_path, output_dir="pixel_stls", pixel_mm=0.3,
            color_height=0.1, total_height=1.0, alignment_pixels=False):
    """Write new STL parts and a palette manifest; never overwrite existing files."""
    if not all(math.isfinite(v) and v > 0 for v in (pixel_mm, color_height, total_height)):
        raise ValueError("Dimensions must be finite positive numbers")
    if total_height <= color_height:
        raise ValueError("Total height must exceed color height")
    with Image.open(input_path) as img:
        if img.format != "PNG" or img.mode != "P":
            raise ValueError("Input must be an indexed/paletted PNG (Pillow mode P)")
        # Reject alpha rather than silently printing invisible palette entries.
        if np.any(np.asarray(img.convert("RGBA"))[:, :, 3] != 255):
            raise ValueError("Transparent pixels are not supported; flatten the image in GIMP first")
        indices = np.flipud(np.asarray(img).copy())
        palette = img.getpalette("RGB")
        width, height = img.size
    used = [int(i) for i in np.unique(indices)]
    if not palette or not used or max(used) * 3 + 2 >= len(palette):
        raise ValueError("Image has an invalid or missing palette")
    parts = []
    for i in used:
        rgb = palette[i*3:i*3+3]
        parts.append({"index": i, "rgb": rgb, "pixels": int(np.count_nonzero(indices == i)),
                      "file": f"color_{i:02d}_{rgb[0]:03d}_{rgb[1]:03d}_{rgb[2]:03d}.stl"})
    output = Path(output_dir)
    # A dedicated empty directory prevents stale color parts from previous runs.
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output directory must be empty or new (prevents stale or overwritten parts)")
    width_mm, height_mm = width * pixel_mm, height * pixel_mm
    summary = {"image_size": [width, height], "size_mm": [width_mm, height_mm, total_height],
               "pixel_mm": pixel_mm, "color_height": color_height, "parts": parts,
               "backing": "backing.stl"}
    summary["alignment_pixels"] = alignment_pixels
    if alignment_pixels:
        summary["alignment_bounds_xy_mm"] = [
            [-2*pixel_mm, -2*pixel_mm],
            [max(width_mm, (len(parts)+1)*pixel_mm)+2*pixel_mm,
             max(height_mm, (len(parts)+1)*pixel_mm)+2*pixel_mm]]
    output.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for slot, part in enumerate(parts):
            mesh = pixel_mesh(indices == part["index"], pixel_mm, color_height)
            if alignment_pixels:
                mesh = trimesh.util.concatenate([mesh, alignment_markers(
                    width_mm, height_mm, pixel_mm, slot, len(parts)+1, color_height)])
            target = output / part["file"]
            with target.open("xb") as stream:
                created.append(target)
                stream.write(mesh.export(file_type="stl"))
        backing = trimesh.creation.box(extents=(width_mm, height_mm, total_height-color_height))
        backing.apply_translation((width_mm/2, height_mm/2, (total_height+color_height)/2))
        if alignment_pixels:
            backing = trimesh.util.concatenate([backing, alignment_markers(
                width_mm, height_mm, pixel_mm, len(parts), len(parts)+1, total_height)])
        target = output / "backing.stl"
        with target.open("xb") as stream:
            created.append(target)
            stream.write(backing.export(file_type="stl"))
        target = output / "palette.json"
        with target.open("x", encoding="utf-8") as stream:
            created.append(target)
            json.dump(summary, stream, indent=2)
            stream.write("\n")
    except BaseException:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Indexed PNG exported from GIMP")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("pixel_stls"))
    parser.add_argument("--pixel-mm", type=float, default=0.3)
    parser.add_argument("--color-height", type=float, default=0.1)
    parser.add_argument("--total-height", type=float, default=1.0)
    parser.add_argument("--alignment-pixels", action="store_true",
                        help="Add disposable external pixels giving all parts identical XY bounds")
    args = parser.parse_args(argv)
    try:
        result = convert(args.input, args.output_dir, args.pixel_mm, args.color_height,
                         args.total_height, args.alignment_pixels)
    except (ValueError, OSError, Image.DecompressionBombError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Image: {result['image_size'][0]} x {result['image_size'][1]} pixels")
    print("Model: " + " x ".join(f"{v:g}" for v in result["size_mm"]) + " mm")
    print(f"Colors: {len(result['parts'])}")
    if args.alignment_pixels:
        bounds = result["alignment_bounds_xy_mm"]
        print(f"With alignment pixels: {bounds[1][0]-bounds[0][0]:g} x "
              f"{bounds[1][1]-bounds[0][1]:g} mm; discard external markers after printing")
    for part in result["parts"]:
        print(f"  {part['file']}  RGB{tuple(part['rgb'])}  {part['pixels']} pixels")
    print(f"Written to {args.output_dir}: color parts, backing.stl, palette.json")
    print("Import all STLs together as one object with multiple parts; assign filaments in Bambu Studio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
