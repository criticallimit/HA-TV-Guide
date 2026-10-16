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
        with tempfile.TemporaryDirectory() as folder:
            backend = module('guide_runtime').GuideRuntime(Path(folder), {'country':'it'}, {'language':'it'}, lambda: None)
            try:
                store = backend.runtime.STORE
                # Independent samples from all three real providers, including the renamed LA7D.
                samples = [
                    [('Rai1.it','Rai 1'),('Rai4.it','Rai 4'),('La7D.it','La7d'),('SkyTG24.it','Sky TG24')],
                    [('Rai 1.it','Rai 1'),('Rai 4.it','Rai 4'),('LA7 Cinema.it','La7 Cinema'),('SKY TG24.it','Sky TG24')],
                    [('Rai.1.HD..101.it','IT - Rai 1 HD'),('Rai.4..5021.it','IT - Rai 4'),('LA7.CINEMA.it','IT - LA7 CINEMA'),('Sky.TG24.it','IT - Sky TG24')],
                ]
                for identities in samples:
                    # A matching display-name must not steal a main station's identity.
                    identities = [('Rai1Regional.it','IT - Rai 1'), *identities]
                    xml = '<tv>' + ''.join('<channel id="'+escape(cid, {'"':'&quot;'})+'"><display-name>'+escape(name)+'</display-name></channel>' for cid,name in identities)
                    xml += ''.join('<programme channel="'+escape(cid, {'"':'&quot;'})+'" start="20300101120000 +0100" stop="20300101130000 +0100"><title>Programme</title></programme>' for cid,_ in identities)+'</tv>'
                    with patch.object(store,'_open_xml',side_effect=lambda:io.BytesIO(xml.encode())):
                        rows=store._parse()
                    main=[c for c in rows if c.get('preset')]
                    self.assertEqual(len(main),45)
                    self.assertEqual({c['id'] for c in main if c['programs']},{'it_rai1','it_rai4','it_la7cinema','it_skytg24'})
                    extra=next(c for c in rows if not c.get('preset'))
                    self.assertEqual(extra['source_name'],'Rai 1')
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
