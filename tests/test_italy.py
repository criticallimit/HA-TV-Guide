"""Italian source identities, provider cleanup, logo coverage and publication."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
from native_support import module

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/tv_guide'


class ItalyTests(unittest.TestCase):
    def test_real_provider_aliases_and_unrelated_regional_station(self):
        catalog = json.loads((COMPONENT / 'catalogs/channels_it.json').read_text())['channels']
        with tempfile.TemporaryDirectory() as folder:
            backend = module('guide_runtime').GuideRuntime(Path(folder), {'country':'it'}, {'language':'it'}, lambda: None)
            try:
                store = backend.runtime.STORE
                # Exercise each provider identity independently, preserving regional extras.
                for rank in range(3):
                    identities = [(c['xmltv_ids'][min(rank,len(c['xmltv_ids'])-1)],c['name']) for c in catalog]
                    identities.append(('Rai1Regional.it','IT - Rai 1 Regional'))
                    xml = '<tv>' + ''.join('<channel id="'+escape(cid, {'"':'&quot;'})+'"><display-name>'+escape(name)+'</display-name></channel>' for cid,name in identities)
                    xml += ''.join('<programme channel="'+escape(cid, {'"':'&quot;'})+'" start="20300101120000 +0100" stop="20300101130000 +0100"><title>Programme</title></programme>' for cid,_ in identities)+'</tv>'
                    with patch.object(store,'_open_xml',side_effect=lambda:io.BytesIO(xml.encode())):
                        rows=store._parse()
                    main=[c for c in rows if c.get('preset')]
                    self.assertEqual(len(main),45)
                    self.assertTrue(all(len(c['programs'])==1 for c in main))
                    extra=next(c for c in rows if not c.get('preset'))
                    self.assertEqual(extra['source_name'],'Rai 1 Regional')
            finally:
                backend.close()

    def test_complete_theme_assets_and_documented_country(self):
        catalog=json.loads((COMPONENT/'catalogs/channels_it.json').read_text())['channels']
        logos=json.loads((COMPONENT/'frontend/app/logo_catalog.json').read_text())['it']
        self.assertEqual(set(logos),{c['id'] for c in catalog})
        for channel in catalog:
            for theme in ('light','dark'):
                svg=(COMPONENT/f"frontend/app/logos/it-{channel['id']}-{theme}.svg").read_text()
                self.assertIn('data:image/',svg)
                self.assertNotIn('href="https:',svg)
        for path in [ROOT/'README.md',ROOT/'info.md']:
            self.assertIn('flags/it.svg',path.read_text())
        for path in [* (ROOT/'docs').glob('*.html'),* (ROOT/'docs/manuals').glob('*.html')]:
            if path.name in ('404.html','screenshots.html'):
                continue
            self.assertIn('data-country="it"',path.read_text(),str(path))
