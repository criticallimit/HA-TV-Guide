"""Complete packaged logo assets, deduplication, self-contained SVG and path safety."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from hashlib import sha256
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components/tv_guide'
spec=importlib.util.spec_from_file_location('_tvguide_logo_assets_tests',ROOT/'logo_assets.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class LogoAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.library=module.LogoLibrary()

    def test_complete_library_and_all_unique_objects_have_verified_bytes(self):
        self.assertEqual(len(self.library.entries),20292)
        expected={item['member']:item['sha256'] for item in self.library.entries.values()}
        found={}
        for path in sorted(self.library.root.glob('logos-*.zip')):
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():found[name]=sha256(archive.read(name)).hexdigest()
        self.assertEqual(found,expected)
        self.assertLess(len(found),len(self.library.entries))

    def test_europe_svg_embeds_local_png_and_requires_no_other_requests(self):
        source=next(key for key in self.library.entries if key.startswith('logos/europe/light/'))
        data,mime=self.library.render(source)
        self.assertEqual(mime,'image/svg+xml')
        self.assertIn(b'href="data:image/',data)
        self.assertNotIn(b'../assets/',data)

    def test_unknown_paths_and_traversal_never_read_external_files(self):
        for source in ('../options.json','logos/../../options.json','/etc/passwd','https://example.org/logo.png'):
            with self.assertRaises(KeyError):self.library.read(source)

    def test_png_normalization_matches_original_canvas(self):
        source=next(key for key in self.library.entries if key.endswith('.png'))
        data,mime=self.library.render(source,True)
        self.assertEqual(mime,'image/svg+xml')
        self.assertIn(b'viewBox="0 0 260 64"',data)
        self.assertIn(b'width="250" height="56"',data)
        self.assertIn(b'data:image/png;base64,',data)
