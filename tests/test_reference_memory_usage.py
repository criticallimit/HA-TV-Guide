"""Bound XML parsing and retain only programme stores that are actually needed."""
import importlib
import importlib.util
import json
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reference_support import app


class MemoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        paths = patch.multiple(app, OPTIONS_FILE=self.root / "options.json",
                               CHANNEL_PREFS_FILE=self.root / "order.json",
                               CACHE_FILE=self.root / "feed.xml", PARSED_CACHE_FILE=self.root / "parsed.json")
        paths.start()
        self.addCleanup(paths.stop)
        self.active = app.EPGStore("de")
        self.registry = {"de": self.active}
        registry = patch.multiple(app, STORE=self.active, COUNTRY_STORES=self.registry)
        registry.start()
        self.addCleanup(registry.stop)
        personal = patch.object(app, "PERSONAL_CHANNELS", importlib.import_module(type(app).__module__.rsplit(".",1)[0] + ".personal_channels").PersonalChannels(app))
        personal.start()
        self.addCleanup(personal.stop)

    def test_channel_scan_memory_does_not_scale_with_programme_descriptions(self):
        source = self.root / "large.xml"
        with source.open("w", encoding="utf-8") as target:
            target.write('<tv><channel id="ard"><display-name>Das Erste</display-name></channel>')
            record = '<programme channel="ard"><title>Title</title><desc>' + "x" * 2048 + '</desc></programme>'
            for _ in range(10000):
                target.write(record)
            # Channel records after programmes must also survive streaming cleanup.
            target.write('<channel id="extra"><display-name>Extra</display-name></channel></tv>')
        with patch.object(self.active, "_open_xml", side_effect=lambda: source.open("rb")):
            tracemalloc.start()
            try:
                channels = self.active._build_channel_map()
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
        self.assertEqual(len(channels), 2)
        self.assertLess(peak, 4 * 1024 * 1024, f"Channel-only scan retained {peak} bytes")

    def test_missing_cache_file_during_stat_is_handled(self):
        with patch.object(self.active.parsed_cache_file.__class__, "exists", side_effect=AssertionError("redundant exists check")), \
             patch.object(self.active.parsed_cache_file.__class__, "stat", side_effect=FileNotFoundError):
            self.active.cache_schema_current = True
            self.active.source_metrics = [{"source": "fixture"}]
            self.assertFalse(self.active._cache_fresh())

    def test_refresh_backoff_avoids_expensive_cache_scan(self):
        self.active.refresh_running = True
        with patch.object(self.active, "_cache_fresh", side_effect=AssertionError("cache scanned")):
            self.active.ensure_fresh_async()
        self.active.refresh_running = False
        self.active.last_refresh_attempt = __import__("time").time()
        with patch.object(self.active, "_cache_fresh", side_effect=AssertionError("cache scanned")):
            self.active.ensure_fresh_async()

    def test_unused_stores_are_released_but_selection_and_refresh_are_preserved(self):
        selected = app.EPGStore("at")
        refreshing = app.EPGStore("ch")
        unused = app.EPGStore("nl")
        self.registry.update(at=selected, ch=refreshing, nl=unused)
        refreshing.refresh_running = True
        app.PERSONAL_CHANNELS.save(["at:" + selected.channels[0]["id"]], [], self.active)
        self.assertEqual(set(self.registry), {"de", "at", "ch"})
        refreshing.refresh_running = False
        with app.SETTINGS_LOCK:
            app.prune_country_stores()
        self.assertEqual(set(self.registry), {"de", "at"})
        app.PERSONAL_CHANNELS.save([], [], self.active)
        self.assertEqual(set(self.registry), {"de"})


    def test_request_with_evicted_store_cannot_start_a_duplicate_refresh(self):
        retired = app.EPGStore("at")
        replacement = app.EPGStore("at")
        self.registry["at"] = replacement
        with patch.object(app, "start_background") as worker:
            retired.ensure_fresh_async()
        worker.assert_not_called()
        self.assertFalse(retired.refresh_running)

    def test_evicted_country_restores_programmes_from_disk_without_network(self):
        store = app.EPGStore("at")
        record = {"title": "Saved programme", "start": "2030-01-01T20:00:00+01:00",
                  "end": "2030-01-01T21:00:00+01:00", "desc": "Saved description"}
        store.channels[0].update(available=True, programs=[record])
        store._save_parsed_cache("fixture")
        before = store.parsed_cache_file.read_bytes()
        self.registry["at"] = store
        with app.SETTINGS_LOCK:
            app.prune_country_stores()
        self.assertNotIn("at", self.registry)
        with patch.object(app.EPGStore, "_download", side_effect=AssertionError("Reload used the network")):
            restored = app.PERSONAL_CHANNELS.country_store("at")
        self.assertIsNot(restored, store)
        self.assertEqual(restored.channels[0]["programs"][0], record)
        self.assertEqual(restored.parsed_cache_file.read_bytes(), before)

    def test_malformed_inactive_country_catalogue_does_not_break_sender_picker(self):
        path=app.country_file(app.PARSED_CACHE_FILE,'at')
        valid={'id':'epg_extra','name':'Extra','programs':[{'title':'Do not retain'}]}
        path.write_text(json.dumps({'country':'at','channels':[valid]}),encoding='utf-8')
        damaged=[{'id':['invalid'],'name':'Broken'},{'id':{'bad':True}},valid,{'id':'epg_nameless','name':None}]
        index=path.with_suffix('.catalogue.json')
        index.write_text(json.dumps({'country':'at','cache_mtime_ns':path.stat().st_mtime_ns,'channels':damaged}),encoding='utf-8')
        with patch.object(app,'EPGStore',side_effect=AssertionError('Inactive catalogue loaded a programme store')):
            catalogue=app.PERSONAL_CHANNELS.catalogue(self.active)
        self.assertEqual(catalogue['at:epg_extra']['name'],'Extra')
        self.assertNotIn('programs',catalogue['at:epg_extra'])
        self.assertEqual(catalogue['at:epg_nameless']['name'],'epg_nameless')
        self.assertNotIn('at:invalid',catalogue)

    def test_legacy_catalogue_upgrade_does_not_keep_programmes_or_load_a_store(self):
        path = app.country_file(app.PARSED_CACHE_FILE, "at")
        path.write_text(json.dumps({"country": "at", "channels": [{
            "id": "epg_extra", "name": "Extra", "programs": [{"title": "Programme"}],
        }]}), encoding="utf-8")
        with patch.object(app, "EPGStore", side_effect=AssertionError("Catalogue loaded a full store")):
            self.assertIn("at:epg_extra", app.PERSONAL_CHANNELS.catalogue(self.active))
        self.assertEqual(set(self.registry), {"de"})
        index = json.loads(path.with_suffix(".catalogue.json").read_text(encoding="utf-8"))
        self.assertNotIn("programs", index["channels"][0])
        # Subsequent settings requests must use the small index, not the full cache.
        original = Path.read_text
        def read_text(candidate, *args, **kwargs):
            if candidate == path:
                raise AssertionError("Warm catalogue read the full programme cache")
            return original(candidate, *args, **kwargs)
        with patch.object(Path, "read_text", read_text):
            self.assertIn("at:epg_extra", app.PERSONAL_CHANNELS.catalogue(self.active))
        path.write_text(json.dumps({"country": "at", "channels": [{"id": "new", "name": "New"}]}), encoding="utf-8")
        self.assertIn("at:new", app.PERSONAL_CHANNELS.catalogue(self.active))
        self.assertNotIn("at:epg_extra", app.PERSONAL_CHANNELS.catalogue(self.active))


if __name__ == "__main__":
    unittest.main()
