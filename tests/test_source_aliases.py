"""Declared aliases share programmes without absorbing regional stations."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from native_support import module


class SourceAliasTests(unittest.TestCase):
    def parse(self, channels, programmes):
        with tempfile.TemporaryDirectory() as folder:
            backend = module('guide_runtime').GuideRuntime(Path(folder), {'country': 'es'}, {'language': 'es'}, lambda: None)
            try:
                xml = '<tv>' + ''.join('<channel id="'+cid+'"><display-name>'+name+'</display-name></channel>' for cid, name in channels)
                for cid, hour, title, description in programmes:
                    xml += '<programme channel="'+cid+'" start="20300101'+hour+'0000 +0000" stop="20300101'+str(int(hour)+1).zfill(2)+'0000 +0000">'+('<title>'+title+'</title>' if title is not None else '')+'<desc>'+description+'</desc></programme>'
                xml += '</tv>'
                with patch.object(backend.runtime.STORE, '_open_xml', side_effect=lambda: io.BytesIO(xml.encode())):
                    return backend.runtime.STORE._parse()
            finally:
                backend.close()

    def test_empty_legacy_alias_does_not_hide_populated_current_alias(self):
        channels = [('324.es', '324'), ('3CatInfo.es', '3CatInfo')]
        for declarations in (channels, list(reversed(channels))):
            with self.subTest(declarations=declarations):
                parsed = self.parse(declarations, [('3CatInfo.es', '12', 'Notícies', '')])
                main = next(ch for ch in parsed if ch['id'] == 'es_3catinfo')
                self.assertEqual([p['title'] for p in main['programs']], ['Notícies'])
                self.assertFalse([ch for ch in parsed if not ch.get('preset')])

    def test_aliases_deduplicate_overlaps_and_keep_complementary_programmes(self):
        parsed = self.parse([('324.es', '324'), ('3CatInfo.es', '3CatInfo')], [
            ('324.es', '12', 'Notícies', ''), ('3CatInfo.es', '12', 'Notícies', 'Detailed news'),
            ('3CatInfo.es', '13', 'Next', '')])
        programmes = next(ch for ch in parsed if ch['id'] == 'es_3catinfo')['programs']
        self.assertEqual([p['title'] for p in programmes], ['Notícies', 'Next'])
        self.assertEqual(programmes[0]['desc'], 'Detailed news')

    def test_missing_title_is_neutral_and_real_source_title_is_preserved(self):
        parsed = self.parse([('LA1.es', 'La 1')], [('LA1.es', '12', None, ''), ('LA1.es', '13', 'Ohne Titel', '')])
        programmes = next(ch for ch in parsed if ch['id'] == 'es_la1')['programs']
        self.assertEqual([p['title'] for p in programmes], ['', 'Ohne Titel'])
