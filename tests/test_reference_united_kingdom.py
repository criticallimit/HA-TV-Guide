"""United Kingdom catalogue, source redundancy and region policy."""
import importlib.util
import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from reference_support import app

class UnitedKingdomTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        paths = patch.multiple(app, OPTIONS_FILE=root / "options.json", CACHE_FILE=root / "feed.xml.gz",
                               PARSED_CACHE_FILE=root / "parsed.json", CHANNEL_PREFS_FILE=root / "order.json")
        paths.start()
        self.addCleanup(paths.stop)

    def parse(self, store, xml):
        with patch.object(store, "_open_xml", side_effect=lambda: io.BytesIO(xml.encode())):
            return store._parse()

    def test_secondary_feed_uses_populated_channel5_hd_instead_of_empty_sd(self):
        xml = '''<tv>
        <channel id="Channel.5.uk"><display-name>Channel 5</display-name></channel>
        <channel id="Channel.5.HD.uk"><display-name>Channel 5 HD</display-name></channel>
        <programme channel="Channel.5.HD.uk" start="20301008190000 +0100" stop="20301008200000 +0100">
        <title>HD programme</title></programme></tv>'''
        channels = self.parse(app.EPGStore("gb"), xml)
        main = next(ch for ch in channels if ch["id"] == "gb_channel5")
        self.assertEqual(main["source_id"], "Channel.5.HD.uk")
        self.assertEqual([p["title"] for p in main["programs"]], ["HD programme"])
        self.assertTrue(any(ch["source_id"] == "Channel.5.uk" and not ch["preset"] for ch in channels))

    def test_regional_names_cannot_replace_london_reference(self):
        xml = '''<tv>
        <channel id="BBCOneScotland.uk"><display-name>BBC One</display-name></channel>
        <channel id="ITV1Granada.uk"><display-name>ITV1</display-name></channel>
        <channel id="BBCOneLondon.uk"><display-name>BBC One London</display-name></channel>
        <channel id="ITV1London.uk"><display-name>ITV1 London</display-name></channel>
        </tv>'''
        channels = self.parse(app.EPGStore("gb"), xml)
        by_id = {ch["id"]: ch for ch in channels}
        self.assertEqual(by_id["gb_bbcone"]["source_id"], "BBCOneLondon.uk")
        self.assertEqual(by_id["gb_itv1"]["source_id"], "ITV1London.uk")
        self.assertEqual({ch["source_id"] for ch in channels if not ch["preset"]},
                         {"BBCOneScotland.uk", "ITV1Granada.uk"})

    def test_xmltv_preserves_actual_duration_across_bst_transitions(self):
        for start, end in [("20301027014500 +0100", "20301027011500 +0000"),
                           ("20300331004500 +0000", "20300331021500 +0100")]:
            with self.subTest(start=start):
                xml = f'''<tv><channel id="BBCOneLondon.uk"/>
                <programme channel="BBCOneLondon.uk" start="{start}" stop="{end}">
                <title>Clock change</title></programme></tv>'''
                channels = self.parse(app.EPGStore("gb"), xml)
                items = next(ch for ch in channels if ch["id"] == "gb_bbcone")["programs"]
                self.assertEqual(len(items), 1)
                duration = datetime.fromisoformat(items[0]["end"]) - datetime.fromisoformat(items[0]["start"])
                self.assertEqual(duration.total_seconds(), 1800)

    def test_either_xmltv_source_can_refresh_without_the_other(self):
        for working_index, source_id in enumerate(["BBCOneLondon.uk", "BBC.One.Lon.HD.uk"]):
            with self.subTest(working_index=working_index):
                store = app.EPGStore("gb")
                xml = f'''<tv><channel id="{source_id}"/>
                <programme channel="{source_id}" start="20301008190000 +0100" stop="20301008200000 +0100">
                <title>Independent source</title></programme></tv>'''
                def download(url):
                    if url != store.source_urls[working_index]:
                        raise OSError("Source unavailable")
                with patch.object(store, "_download", side_effect=download), \
                        patch.object(store, "_open_xml", side_effect=lambda: io.BytesIO(xml.encode())), \
                        patch.object(app, "wake_sensors"):
                    store.refresh(force=True)
                main = next(ch for ch in store.channels if ch["id"] == "gb_bbcone")
                self.assertEqual(main["programs"][0]["title"], "Independent source")
                self.assertEqual([m["ok"] for m in store.source_metrics],
                                 [index == working_index for index in range(2)])
                self.assertIsNone(store.last_error)

    def test_country_registration_and_independent_sources(self):
        config = app.COUNTRIES["gb"]
        self.assertEqual(config["timezone"], "Europe/London")
        self.assertEqual(config["catalog"], "channels_gb.json")
        self.assertEqual(config["sources"], [
            "https://www.open-epg.com/files/unitedkingdom.xml.gz",
            "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz",
        ])

    def test_main_channels_and_london_reference_variants(self):
        catalog = app.COUNTRY_CATALOGS["gb"]["channels"]
        expected = [
            "BBC One", "BBC Two", "ITV1", "Channel 4", "Channel 5",
            "ITV2", "BBC Three", "BBC Four", "ITV3", "E4",
            "Film4", "More4", "ITV4", "U&Dave", "U&Drama",
            "U&Yesterday", "5USA", "Sky Mix", "BBC News", "Sky News",
        ]
        self.assertEqual([item["name"] for item in catalog], expected)
        self.assertEqual([item["order"] for item in catalog], list(range(1, 21)))
        self.assertTrue(all(item["id"].startswith("gb_") for item in catalog))
        self.assertTrue(all(source.endswith(".uk") for item in catalog for source in item["xmltv_ids"]))
        by_id = {item["id"]: item for item in catalog}
        self.assertIn("BBCOneLondon.uk", by_id["gb_bbcone"]["xmltv_ids"])
        self.assertIn("ITV1London.uk", by_id["gb_itv1"]["xmltv_ids"])
        self.assertTrue(all(item.get("xmltv_id_only") for item in catalog))

    def test_curated_channels_have_offline_logos(self):
        for original in app.COUNTRY_CATALOGS["gb"]["channels"]:
            channel = {**original, "source_country": "gb"}
            for theme in ("light", "dark"):
                source = app._logo_source_for_channel(channel, theme)
                self.assertTrue(source, f"{original['name']} / {theme}")
                self.assertFalse(source.startswith(("http://", "https://")))
                self.assertTrue(app.normalized_logo_path(channel, theme).is_file())


if __name__ == "__main__":
    unittest.main()
