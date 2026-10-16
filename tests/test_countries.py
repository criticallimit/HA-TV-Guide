"""Country registration consistency and extension without code changes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'tv_guide'


class CountryRegistrationTests(unittest.TestCase):
    def test_every_registration_has_valid_sources_catalogue_and_provider_ids(self):
        countries = json.loads((ROOT / 'countries.json').read_text())
        for code, item in countries.items():
            with self.subTest(country=code):
                self.assertEqual(len(code), 2)
                ZoneInfo(item['timezone'])
                self.assertTrue(item['name'])
                self.assertTrue(item['sources'])
                self.assertEqual(len(item['sources']), len(set(item['sources'])))
                self.assertTrue(all(url.startswith('https://') for url in item['sources']))
                catalog = json.loads((ROOT / 'catalogs' / item['catalog']).read_text())
                ids = {channel['id'] for channel in catalog['channels']}
                self.assertEqual(len(ids), len(catalog['channels']))
                for key in ('providers', 'secondary_providers', 'secondary_urls', 'teletext_providers'):
                    self.assertLessEqual(set(item.get(key, {})), ids)

    def test_new_registration_derives_all_shared_indexes_without_python_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = ROOT / 'countries.py'
            (root / source.name).write_bytes(source.read_bytes())
            data = json.loads((ROOT / 'countries.json').read_text())
            data['zz'] = {'name': 'New country', 'timezone': 'Pacific/Auckland',
                          'language': 'it', 'catalog': 'channels_zz.json',
                          'sources': ['https://example.org/new.xml.gz', 'https://example.org/backup.xml.gz']}
            (root / 'countries.json').write_text(json.dumps(data))
            spec = importlib.util.spec_from_file_location('_tvguide_extended_countries', root / source.name)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.COUNTRY_NAMES['zz'], 'New country')
            self.assertEqual(module.CATALOG_FILES['zz'], 'channels_zz.json')
            self.assertEqual(module.COUNTRY_FEEDS['zz'], data['zz']['sources'][0])
            self.assertEqual(module.COUNTRY_FALLBACKS['zz'], tuple(data['zz']['sources'][1:]))
            first_italian_country=next(code for code,item in data.items() if item.get('language')=='it')
            self.assertEqual(module.LANGUAGE_COUNTRIES['it'],first_italian_country)
