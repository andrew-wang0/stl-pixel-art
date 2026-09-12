import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
import trimesh

from pixel_art import convert, main, pixel_mesh


class GeometryTests(unittest.TestCase):
    def test_all_small_masks(self):
        # Exhaustive coverage of holes, concave corners, islands, and diagonal contacts.
        for bits in range(1, 512):
            mask = np.array([(bits >> i) & 1 for i in range(9)], dtype=bool).reshape(3, 3)
            mesh = pixel_mesh(mask, 0.4, 0.1)
            self.assertTrue(mesh.is_watertight, bits)
            self.assertTrue(mesh.is_winding_consistent, bits)
            self.assertAlmostEqual(mesh.volume, mask.sum() * 0.016)

    def test_shared_wall_removed(self):
        mesh = pixel_mesh(np.ones((1, 2), dtype=bool), 0.4, 0.1)
        self.assertEqual(len(mesh.faces), 20)  # Two boxes would have 24 triangles.


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "art.png"
        img = Image.new("P", (2, 2))
        img.putpalette([0, 0, 0, 255, 0, 0, 0, 120, 255] + [0] * 759)
        img.putdata([1, 0, 2, 2])
        img.save(self.source)

    def test_alignment_orientation_and_round_trip(self):
        out = self.root / "out"
        summary = convert(self.source, out)
        self.assertEqual([p['pixels'] for p in summary['parts']], [1, 1, 2])
        meshes = {p['index']: trimesh.load_mesh(out / p['file']) for p in summary['parts']}
        np.testing.assert_allclose(meshes[1].bounds, [[0, .4, 0], [.4, .8, .1]])
        np.testing.assert_allclose(meshes[2].bounds, [[0, 0, 0], [.8, .4, .1]])
        backing = trimesh.load_mesh(out / "backing.stl")
        np.testing.assert_allclose(backing.bounds, [[0, 0, .1], [.8, .8, 1]])
        for mesh in [*meshes.values(), backing]:
            self.assertTrue(mesh.is_watertight)
            self.assertTrue(mesh.is_winding_consistent)
        self.assertAlmostEqual(sum(m.volume for m in meshes.values()) + backing.volume, .64, places=6)
        self.assertTrue((out / "palette.json").exists())

    def test_dimensions_and_output_protection(self):
        for kwargs in ({'pixel_mm': 0}, {'pixel_mm': float('nan')},
                       {'color_height': -1}, {'total_height': .1}, {'total_height': float('inf')}):
            with self.assertRaises(ValueError):
                convert(self.source, self.root / 'bad', **kwargs)
        out = self.root / 'out'
        convert(self.source, out, .6, .2, 2)
        original = (out / 'backing.stl').read_bytes()
        with self.assertRaises(ValueError):
            convert(self.source, out)
        self.assertEqual(original, (out / 'backing.stl').read_bytes())

    def test_reject_rgb_and_transparency(self):
        rgb = self.root / 'rgb.png'
        Image.new('RGB', (1, 1)).save(rgb)
        with self.assertRaisesRegex(ValueError, 'indexed'):
            convert(rgb, self.root / 'out')
        with Image.open(self.source) as img:
            img.save(self.root / 'alpha.png', transparency=1)
        with self.assertRaisesRegex(ValueError, 'Transparent'):
            convert(self.root / 'alpha.png', self.root / 'out')

    def test_cli(self):
        self.assertEqual(main([str(self.source), '-o', str(self.root / 'cli')]), 0)
        self.assertEqual(main([str(self.root / 'missing.png')]), 1)


if __name__ == '__main__':
    unittest.main()
