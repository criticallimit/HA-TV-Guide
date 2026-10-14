"""Source isolation, exact dated schedules and cache survival during outages."""

import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
from reference_support import app


class ScheduleResilienceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        paths = patch.multiple(app, OPTIONS_FILE=root / "options.json", CACHE_FILE=root / "feed.xml.gz",
                               PARSED_CACHE_FILE=root / "parsed.json", CHANNEL_PREFS_FILE=root / "order.json")
        paths.start()
        self.addCleanup(paths.stop)

    def tv4_page(self, day):
        state = {
            "ROOT_QUERY": {'schedule(' + json.dumps({"date": day.isoformat()}) + ')': [{"__ref": "Schedule:tv4"}]},
            "Schedule:tv4": {"name": "tv4", "day": day.isoformat(),
                             "broadcasts": [{"__ref": "Broadcast:valid"}, {"__ref": "Broadcast:invalid"}]},
            "Broadcast:valid": {"title": "Night show", "start": f"{day}T23:00:00+02:00",
                                "end": f"{day + timedelta(days=1)}T02:00:00+02:00",
                                "synopsis": {"__ref": "Synopsis:valid"}},
            "Broadcast:invalid": {"title": "Invalid", "start": "bad", "end": "bad"},
            "Synopsis:valid": {"medium": "Programme description"},
        }
        return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"apolloState": state}}) + '</script>'

    def test_tv4_reads_complete_embedded_schedule_not_truncated_visible_listing(self):
        store = app.EPGStore("se")
        day = date(2026, 10, 6)
        rows = store._parse_tv4_schedule(self.tv4_page(day), "tv4", day)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["desc"], "Programme description")
        self.assertEqual(rows[0]["end_dt"].date(), day + timedelta(days=1))
        self.assertEqual(store._parse_tv4_schedule(self.tv4_page(day), "sjuan", day), [])
        self.assertEqual(store._parse_tv4_schedule(self.tv4_page(day), "tv4", day + timedelta(days=1)), [])

    def test_chmedia_rejects_navigation_livebar_wrong_channel_and_stale_page(self):
        store = app.EPGStore("ch")
        day = date(2026, 10, 6)
        page = f'''<nav data-epg-date="{day}"></nav>
        <li data-channel="3plus-movies" data-start="{day}T12:00:00+02:00"><span>Wrong livebar</span></li>
        <div class="epg2__row"><a class="epg2__ch" href="/sender/3plus-movies">Movies</a>
          <div class="epg2__prog" data-epg2-prog data-start="{day}T23:00:00+02:00"
               data-end="{day + timedelta(days=1)}T01:00:00+02:00">
            <span class="epg2__prog-title">Film &amp; More</span></div>
        <div class="epg2__row"><a class="epg2__ch" href="/sender/3plus-series">Series</a>
          <div data-epg2-prog data-start="{day}T23:00:00+02:00" data-end="{day}T23:50:00+02:00">
            <span class="epg2__prog-title">Wrong channel</span></div>'''
        rows = store._parse_chmedia_schedule(page, "3plus-movies", day)
        self.assertEqual([row["title"] for row in rows], ["Film & More"])
        self.assertEqual(rows[0]["end_dt"].date(), day + timedelta(days=1))
        self.assertEqual(store._parse_chmedia_schedule(page, "3plus-movies", day + timedelta(days=1)), [])

    def test_midnight_carryover_survives_one_day_outage_and_naive_times_are_rejected(self):
        store = app.EPGStore("se")
        now = datetime.now(app.EPG_TIMEZONE).replace(hour=0, minute=30, second=0, microsecond=0)
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        def fetch(url, label):
            day = date.fromisoformat(url.rsplit("/", 1)[1])
            if day == now.date():
                raise OSError("One day unavailable")
            return self.tv4_page(day)
        with patch.object(app, "datetime", Clock), patch.object(store, "_fetch_html", side_effect=fetch):
            rows = store._fetch_official_programs("se_tv4", app.COUNTRIES["se"]["providers"]["se_tv4"])
        self.assertTrue(any(datetime.fromisoformat(row["start"]) < now < datetime.fromisoformat(row["end"]) for row in rows))
        def invalid(page, marker, day):
            return [{"title": "No timezone", "start_dt": datetime.combine(day, datetime.min.time()),
                     "end_dt": datetime.combine(day, datetime.min.time()) + timedelta(hours=1)}]
        with patch.object(store, "_parse_tv4_schedule", side_effect=invalid), patch.object(store, "_fetch_html", return_value=""):
            self.assertEqual(store._fetch_regional_programs(app.COUNTRIES["se"]["providers"]["se_tv4"]), [])

    def test_failed_shared_url_is_tried_once_per_refresh_but_retried_next_refresh(self):
        store = app.EPGStore("ch")
        store._official_html_cache = {}
        store._official_fetch_errors = {}
        with patch.object(app, "urlopen", side_effect=OSError("Source down")) as fetch:
            for _ in range(7):
                with self.assertRaises(OSError):
                    store._fetch_html("https://www.3plus.ch/tv-programm/2026/10/06", "3+")
            self.assertEqual(fetch.call_count, 1)
            store._official_fetch_errors = {}
            with self.assertRaises(OSError):
                store._fetch_html("https://www.3plus.ch/tv-programm/2026/10/06", "3+")
            self.assertEqual(fetch.call_count, 2)

    def test_cached_official_data_fills_gaps_but_never_overrides_new_feed_corrections(self):
        store = app.EPGStore("dk")
        now = datetime.now(app.EPG_TIMEZONE)
        def programme(title, start, end):
            return {"title": title, "start": (now + timedelta(hours=start)).isoformat(),
                    "end": (now + timedelta(hours=end)).isoformat(), "_source": "official", "_source_rank": 450}
        old = [programme("Old correction", -1, 1), programme("Still valid", 1, 2), programme("Expired", -3, -2)]
        store.channels[0]["programs"] = old
        store.channels[1]["programs"] = [programme("Source missing", 0, 2)]
        fresh = programme("New correction", -0.5, 0.5)
        fresh.update(_source="xmltv", _source_rank=220)
        channels = [{**channel, "programs": [], "available": False} for channel in store.channels]
        channels[0]["programs"] = [fresh]
        result = store._retain_cached_programmes(channels)
        self.assertEqual([p["title"] for p in result[0]["programs"]], ["New correction", "Still valid"])
        self.assertEqual(result[1]["programs"][0]["title"], "Source missing")
        self.assertEqual(store.channels[0]["programs"], old)

    def test_partial_refresh_keeps_other_channels_without_reusing_expired_programmes(self):
        store = app.EPGStore("dk")
        now = datetime.now(app.EPG_TIMEZONE)
        cached = {"title": "Cached", "start": (now - timedelta(hours=1)).isoformat(),
                  "end": (now + timedelta(hours=2)).isoformat()}
        store.channels[1]["programs"] = [cached]
        fresh = {**cached, "title": "Fresh"}
        channels = [{**channel, "programs": [], "available": False} for channel in store.channels]
        channels[0]["programs"] = [fresh]
        with patch.object(store, "_candidate_urls", return_value=["https://feed.example"]), \
                patch.object(store, "_download"), patch.object(store, "_parse", return_value=channels), \
                patch.object(store, "_validate_feed_quality"), patch.object(store, "_supplement_missing_channels", side_effect=lambda c: c), \
                patch.object(store, "_save_parsed_cache"):
            store.refresh(force=True)
        channel = next(channel for channel in store.channels if channel["id"] == "dk_tv2")
        self.assertEqual(channel["programs"], [cached])

    def test_teletext_failure_does_not_discard_working_official_source(self):
        store = app.EPGStore("de")
        now = datetime.now(app.EPG_TIMEZONE)
        programme = {"title": "Live", "start": now.isoformat(), "end": (now + timedelta(hours=1)).isoformat()}
        channels = [{"id": "ard", "name": "Das Erste", "programs": []}]
        with patch.object(app, "base_channel_ids", return_value=["ard"]), \
                patch.object(store, "_fetch_official_programs", return_value=[programme]), \
                patch.object(store, "_fetch_teletext_programs", side_effect=OSError("Teletext unavailable")), \
                patch.object(store, "_fetch_secondary_web_programs", return_value=[]):
            result = store._supplement_missing_channels(channels)
        self.assertEqual(result[0]["programs"][0]["title"], "Live")
        self.assertEqual(store.official_metrics["provider_results"]["ard"]["status"], "ok")

    def test_new_swiss_feed_names_resolve_to_existing_saved_channel_ids(self):
        store = app.EPGStore("ch")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feed.xml"
            path.write_text('<tv><channel id="3+ Movies.ch"><display-name>3+ Movies</display-name></channel></tv>')
            with patch.object(store, "_open_xml", side_effect=lambda: path.open("rb")):
                self.assertEqual(store._build_channel_map()["ch_4"]["xmltv_id"], "3+ Movies.ch")


if __name__ == "__main__":
    unittest.main()
