"""Spanish real source identities, theme artwork and independent HA defaults."""
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

class SpainTests(unittest.TestCase):
    def test_four_real_feed_identity_sets_and_unrelated_regional_channels(self):
        samples=json.loads((ROOT/'tests/fixtures/spain-channel-identities.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            backend=module('guide_runtime').GuideRuntime(Path(folder),{'country':'es'},{'language':'es'},lambda:None)
            try:
                store=backend.runtime.STORE
                for feed,identities in samples.items():
                    with self.subTest(feed=feed):
                        rows=[('La1Regional.es','ES - La 1'),('TV3Cat.es','ES - TV3CAT')]+[(item['source_id'],item['name']) for item in identities]
                        xml='<tv>'+''.join('<channel id="'+escape(cid,{'"':'&quot;'})+'"><display-name>'+escape(name)+'</display-name></channel>' for cid,name in rows)
                        xml+=''.join('<programme channel="'+escape(cid,{'"':'&quot;'})+'" start="20300101120000 +0000" stop="20300101130000 +0000"><title>Programa</title></programme>' for cid,_ in rows)+'</tv>'
                        with patch.object(store,'_open_xml',side_effect=lambda:io.BytesIO(xml.encode())):parsed=store._parse()
                        main=[channel for channel in parsed if channel.get('preset')]
                        self.assertEqual(len(main),48)
                        self.assertEqual({channel['id'] for channel in main if channel['programs']},{item['id'] for item in identities})
                        extras=[channel for channel in parsed if not channel.get('preset')]
                        self.assertEqual({channel['source_name'] for channel in extras},{'La 1','TV3CAT'})
                        for channel in main:
                            if channel['programs']:
                                self.assertEqual(datetime.fromisoformat(channel['programs'][0]['start']).astimezone(timezone.utc).hour,12)
            finally:backend.close()

    def test_spanish_auto_defaults_and_entity_notifications(self):
        defaults=module('ha_defaults').installation_defaults
        self.assertEqual(defaults(types.SimpleNamespace(country='ES',language='es-ES'))['country'],'es')
        self.assertEqual(defaults(types.SimpleNamespace(country=None,language='es_MX'))['country'],'es')
        self.assertEqual(defaults(types.SimpleNamespace(country='DE',language='es'))['country'],'de')
        text=module('notification_text').reminder_text({'language':'es','channel':'La 1','title':'Noticias'},'20:15')
        self.assertEqual(text['title'],'TV Guide – Recordatorio')
        self.assertIn('empieza a las 20:15',text['message'])

    def test_reproducible_artwork_and_published_country(self):
        result=subprocess.run([sys.executable,str(ROOT/'tools/build_logo_artwork.py'),str(COMPONENT/'catalogs/spain_logo_sources.json'),'--check'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for path in [ROOT/'README.md',ROOT/'info.md']:self.assertIn('🇪🇸 Spain',path.read_text())
        for path in [*(ROOT/'docs').glob('*.html'),*(ROOT/'docs/manuals').glob('*.html')]:
            if path.name not in ('404.html','screenshots.html'):self.assertIn('data-country="es"',path.read_text(),str(path))
