"""A single downloaded logo database for main channels, legacy clients and extras."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from native_support import module

ROOT=Path(__file__).resolve().parents[1]
COMPONENT=ROOT/'custom_components/tv_guide'
assets=module('logo_assets')


class CentralLogoTests(unittest.TestCase):
    def setUp(self):
        self.library=assets.LogoLibrary()
        self.library.archive_root=ROOT/'tests/fixtures/logo-samples'

    def test_all_main_channel_variants_exist_only_in_downloaded_packages(self):
        self.assertFalse((COMPONENT/'frontend/app/logos').exists())
        self.assertFalse((COMPONENT/'frontend/app/logo_catalog.json').exists())
        self.assertFalse(list((COMPONENT/'logo_library').glob('logos-*.zip')))
        countries=json.loads((COMPONENT/'countries.json').read_text())
        for country,config in countries.items():
            catalog=json.loads((COMPONENT/'catalogs'/config['catalog']).read_text())
            for channel in catalog['channels']:
                urls=self.library.channel_urls(country,channel['id'])
                self.assertEqual(set(urls),{'logo_normalized_light','logo_normalized_dark'})
                for url in urls.values():
                    source=url.split('/tv_guide/logo/')[1].split('?')[0]
                    self.assertIn('?v='+self.library.revision,url)
                    data,mime=self.library.render(source)
                    self.assertEqual(sha256(data).hexdigest(),self.library.entries[source]['sha256'])
                    self.assertEqual(mime,'image/svg+xml')
                    self.assertNotIn(b'href="https:',data)
                    self.assertNotIn(b'href="../',data)

    def test_legacy_client_sources_alias_the_same_current_artwork(self):
        with tempfile.TemporaryDirectory() as folder:
            backend=module('guide_runtime').GuideRuntime(Path(folder),{'country':'de'},{'language':'de'},lambda:None)
            try:
                for country,catalog in backend.runtime.COUNTRY_CATALOGS.items():
                    for channel in catalog['channels']:
                        themes=self.library.channels[country+':'+channel['id']]
                        for theme,source in themes.items():
                            legacy=backend.runtime._logo_source_for_channel({**channel,'source_country':country},theme)
                            self.assertEqual(self.library.entries[legacy]['sha256'],self.library.entries[source]['sha256'],(country,channel['id'],theme))
            finally:backend.close()

    def test_invalid_channel_mapping_is_rejected_before_activation(self):
        index=json.loads((COMPONENT/'logo_library/index.json').read_text())
        before=self.library.revision
        for themes in ({'dark':'missing.svg'},{'light':'missing.svg','dark':'missing.svg'},'broken'):
            changed={**index,'channels':{'it:it_rai1':themes}}
            with self.assertRaises(ValueError):self.library.activate(changed,self.library.archive_root)
            self.assertEqual(self.library.revision,before)
            self.assertIn('it:it_rai1',self.library.channels)
