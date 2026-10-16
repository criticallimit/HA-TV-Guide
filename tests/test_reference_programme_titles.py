"""RTL programme/episode semantics and rejection of obsolete derived caches."""
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from reference_support import app


def page(records):
    flight = '5:' + json.dumps({'items': records}) + '\n'
    midpoint = len(flight) // 2
    return ''.join('<script>self.__next_f.push([1,' + json.dumps(chunk) + '])</script>' for chunk in [flight[:midpoint], flight[midpoint:]])


def record(name, alternate, **extra):
    return dict(name=name, alternateName=alternate, broadcastService='VOX', type='BroadcastEvent',
                startDate='2026-10-04T15:00Z', endDate='2026-10-04T16:10Z', **extra)


class ProgrammeTitleTests(unittest.TestCase):
    def setUp(self):
        self.store = app.EPGStore("de")

    def test_programme_name_precedes_episode_for_all_shared_channels(self):
        for channel, service in [('rtl', 'RTL'), ('vox', 'VOX'), ('nitro', 'NITRO'),
                                 ('rtlup', 'RTLup'), ('voxup', 'VOXup'), ('superrtl', 'SUPER RTL')]:
            with self.subTest(channel=channel):
                event = record('Programme name', 'Episode 4')
                event['broadcastService'] = service
                parsed = self.store._parse_rtl_programmes(page([event]), channel, date(2026, 10, 4))
                self.assertEqual([(p['title'], p['subtitle']) for p in parsed], [('Programme name', 'Episode 4')])

    def test_vox_magazine_keeps_date_as_subtitle(self):
        event = record('auto mobil - Das VOX Automagazin', 'Sendung vom 04.10.2026',
                       workFeatured=[{'name': 'Sendung vom 04.10.2026', 'partOfSeries': {'name': 'auto mobil - Das VOX Automagazin'}}])
        parsed = self.store._parse_rtl_programmes(page([event]), 'vox', date(2026, 10, 4))
        self.assertEqual(parsed[0]['title'], event['name'])
        self.assertEqual(parsed[0]['subtitle'], event['alternateName'])
        self.assertEqual(parsed[0]['start'], '2026-10-04T17:00:00+02:00')

    def test_series_metadata_resolves_different_outer_field_order(self):
        work = {'name': 'Episode title', 'partOfSeries': {'name': 'Series title'}}
        for name, alternate in [('Series title', 'Episode title'), ('Episode title', 'Series title')]:
            with self.subTest(name=name):
                parsed = self.store._parse_rtl_programmes(page([record(name, alternate, workFeatured=[work])]), 'vox', date(2026, 10, 4))
                self.assertEqual((parsed[0]['title'], parsed[0]['subtitle']), ('Series title', 'Episode title'))

    def test_movies_without_series_name_and_repeated_titles(self):
        for name, alternate, expected in [(None, 'Movie title', ('Movie title', '')),
                                          ('Movie title', None, ('Movie title', '')),
                                          ('Movie title', 'Movie title', ('Movie title', ''))]:
            with self.subTest(name=name, alternate=alternate):
                parsed = self.store._parse_rtl_programmes(page([record(name, alternate)]), 'vox', date(2026, 10, 4))
                self.assertEqual((parsed[0]['title'], parsed[0]['subtitle']), expected)

    def test_live_navigation_widget_is_not_merged_with_the_daily_schedule(self):
        teaser = record('Episode title', 'Series title')
        teaser['type'] = 'SHOW_EPISODE'
        schedule = record('Series title', 'Episode title')
        parsed = self.store._parse_rtl_programmes(page([teaser, schedule]), 'vox', date(2026, 10, 4))
        self.assertEqual([(p['title'], p['subtitle']) for p in parsed], [('Series title', 'Episode title')])
        self.assertEqual(self.store._parse_rtl_programmes(page([teaser]), 'vox', date(2026, 10, 4)), [])

    def test_obsolete_caches_are_discarded_instead_of_migrated(self):
        programme = {'title':'Cached programme','start':'2026-10-04T12:00:00+02:00','end':'2026-10-04T13:00:00+02:00'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'parsed.json'
            for version in [0, 5, 6, 7, 9, app.PARSED_CACHE_SCHEMA_VERSION]:
                with self.subTest(version=version):
                    path.write_text(json.dumps({'schema_version':version,'country':'de',
                        'channels':[{'id':'vox','programs':[programme]}]}),encoding='utf-8')
                    index = path.with_suffix('.catalogue.json')
                    index.write_text('{}',encoding='utf-8')
                    with patch.object(app,'PARSED_CACHE_FILE',path):
                        self.assertEqual(self.store._load_parsed_cache(),version == app.PARSED_CACHE_SCHEMA_VERSION)
                    current = version == app.PARSED_CACHE_SCHEMA_VERSION
                    self.assertEqual(path.exists(),current)
                    self.assertEqual(index.exists(),current)
                    self.assertEqual(self.store.cache_schema_current,current)


if __name__ == '__main__':
    unittest.main()
