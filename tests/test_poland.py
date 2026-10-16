"""Polish real source identities, theme artwork and independent HA defaults."""
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
from native_support import module

ROOT=Path(__file__).resolve().parents[1]
COMPONENT=ROOT/'custom_components/tv_guide'

class PolandTests(unittest.TestCase):
    def test_three_real_feed_identity_sets_and_unrelated_regional_channels(self):
        samples=json.loads((ROOT/'tests/fixtures/poland-channel-identities.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            backend=module('guide_runtime').GuideRuntime(Path(folder),{'country':'pl'},{'language':'pl'},lambda:None)
            try:
                store=backend.runtime.STORE
                for feed,identities in samples.items():
                    with self.subTest(feed=feed):
                        rows=[('TVP3Warszawa.pl','PL - TVP 3 Warszawa'),('TVP3Krakow.pl','PL - TVP 3 Kraków'),('Eurosport1Niem.pl','PL - Eurosport 1 (niem.)')]+[(item['source_id'],item['name']) for item in identities]
                        xml='<tv>'+''.join('<channel id="'+escape(cid,{'"':'&quot;'})+'"><display-name>'+escape(name)+'</display-name></channel>' for cid,name in rows)
                        xml+=''.join('<programme channel="'+escape(cid,{'"':'&quot;'})+'" start="20300101120000 +0000" stop="20300101130000 +0000"><title>Program</title></programme>' for cid,_ in rows)+'</tv>'
                        with patch.object(store,'_open_xml',side_effect=lambda:io.BytesIO(xml.encode())):parsed=store._parse()
                        main=[channel for channel in parsed if channel.get('preset')]
                        self.assertEqual(len(main),50)
                        self.assertEqual({channel['id'] for channel in main if channel['programs']},{item['id'] for item in identities})
                        extras=[channel for channel in parsed if not channel.get('preset')]
                        self.assertEqual({channel['source_name'] for channel in extras},{'TVP 3 Warszawa','TVP 3 Kraków','Eurosport 1 (niem.)'})
                        for channel in main:
                            if channel['programs']:
                                self.assertEqual(datetime.fromisoformat(channel['programs'][0]['start']).astimezone(timezone.utc).hour,12)
            finally:backend.close()

    def test_polish_auto_defaults_and_entity_notifications(self):
        defaults=module('ha_defaults').installation_defaults
        self.assertEqual(defaults(types.SimpleNamespace(country='PL',language='pl-PL'))['country'],'pl')
        self.assertEqual(defaults(types.SimpleNamespace(country=None,language='pl_PL'))['country'],'pl')
        self.assertEqual(defaults(types.SimpleNamespace(country='DE',language='pl'))['country'],'de')
        text=module('notification_text').reminder_text({'language':'pl','channel':'TVP 1','title':'Wiadomości'},'20:15')
        self.assertEqual(text['title'],'TV Guide – Przypomnienie')
        self.assertIn('zaczyna się o 20:15',text['message'])

    def test_polish_personal_order_survives_country_language_changes_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            order = ['pl:pl_tvn', 'de:ard', 'pl:pl_tvp1']
            for iteration in range(2):
                backend = module('guide_runtime').GuideRuntime(Path(folder), {'country':'pl'}, {'language':'pl'}, lambda:None)
                try:
                    backend.runtime.start_background = lambda *args, **kwargs: None
                    if iteration == 0:
                        backend.request('personal-channels', 'POST', {'order':order, 'countries':['pl','de']})
                        settings = backend.request('settings', 'GET')
                        for country, language in [('de','en'), ('es','es'), ('pl','pl')]:
                            result = backend.request('settings', 'POST', {**settings, 'country':country, 'language':language})
                            self.assertTrue(result['ok'])
                    self.assertEqual(backend.request('personal-channels', 'GET')['order'], order)
                    self.assertEqual(backend.request('settings', 'GET')['language'], 'pl')
                    guide = backend.request('guide', 'GET')
                    self.assertEqual(guide['custom_channel_ids'], order)
                    self.assertEqual(guide['country'], 'pl')
                finally:
                    backend.close()

    def test_reproducible_artwork_and_published_country(self):
        result=subprocess.run([sys.executable,str(ROOT/'tools/build_logo_artwork.py'),str(COMPONENT/'catalogs/poland_logo_sources.json'),'--check'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for path in [ROOT/'README.md',ROOT/'info.md']:self.assertIn('flags/pl.svg',path.read_text())
        for path in [*(ROOT/'docs').glob('*.html'),*(ROOT/'docs/manuals').glob('*.html')]:
            if path.name not in ('404.html','screenshots.html'):self.assertIn('data-country="pl"',path.read_text(),str(path))
