"""Norwegian schedules must retain dates, station identity and source priority."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from reference_support import app


class NorwayTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        paths = patch.multiple(app, OPTIONS_FILE=root / "options.json", CACHE_FILE=root / "feed.xml.gz",
                               PARSED_CACHE_FILE=root / "parsed.json", CHANNEL_PREFS_FILE=root / "order.json")
        paths.start()
        self.addCleanup(paths.stop)
        self.store = app.EPGStore("no")

    def test_public_json_requests_negotiate_the_documented_formats(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"[]"
        response.headers.get_content_charset.return_value = "utf-8"
        for url, expected in [("https://psapi.nrk.no/tv/epg/nrk1?date=2026-10-04", "application/vnd.nrk.epg.v2+json"),
                              ("https://tv2no-epg-api.public.tv2.no/epg/days/2026/10/04", "application/json")]:
            with patch.object(app, "urlopen", return_value=response) as fetch:
                self.assertEqual(self.store._fetch_html(url, "Schedule"), "[]")
            self.assertEqual(fetch.call_args.args[0].get_header("Accept"), expected)

    def test_tv2_requires_matching_date_station_and_valid_intervals(self):
        provider = app.COUNTRIES["no"]["providers"]["no_tv2direkte"]
        def fetch(url, label):
            day = datetime.strptime(url.rsplit("/days/", 1)[1], "%Y/%m/%d").date().isoformat()
            valid = {"title": "Live", "startTime": day + "T20:30:00", "endTime": day + "T21:15:17"}
            rows = [valid, {"title": "Broken", "startTime": "bad"},
                    {**valid, "title": "Reversed", "endTime": day + "T20:00:00"},
                    {**valid, "title": "Stale", "startTime": "2000-01-01T20:30:00"}]
            return json.dumps([
                {"channelId": "TV2DIR", "date": day, "channel": {}, "programs": rows},
                {"channelId": "TV2DIR", "date": "2000-01-01", "programs": [valid]},
                {"channelId": "OTHER", "date": day, "programs": [valid]},
                {"channelId": "TV2DIR", "date": day, "channel": {"disabled": True}, "programs": [valid]},
            ])
        with patch.object(self.store, "_fetch_html", side_effect=fetch):
            rows = self.store._fetch_official_programs("no_tv2direkte", provider)
        self.assertEqual([row["title"] for row in rows], ["Live"] * 3)
        for row in rows:
            start, end = map(datetime.fromisoformat, (row["start"], row["end"]))
            self.assertEqual(start.hour, 20)
            self.assertEqual(start.utcoffset(), start.astimezone(ZoneInfo("Europe/Oslo")).utcoffset())
            self.assertEqual(end - start, timedelta(minutes=45, seconds=17))

    def test_nrk_rejects_wrong_stream_stale_naive_and_broken_entries(self):
        provider = app.COUNTRIES["no"]["providers"]["no_nrk3"]
        def fetch(url, label):
            day = url.split("date=", 1)[1]
            valid = {"title": "NRK 3 evening", "start": {"planned": day + "T20:30:00+02:00"},
                     "end": {"planned": day + "T21:15:00+02:00"}}
            entries = [valid, {"title": "Broken"},
                       {**valid, "start": {"planned": day + "T20:30:00"}},
                       {**valid, "start": {"planned": "2000-01-01T20:30:00+02:00"}}]
            return json.dumps([
                {"channelId": "nrk3", "hasPublicEpg": True, "transmissionGroups": [{"entries": entries}]},
                {"channelId": "nrksuper", "hasPublicEpg": True, "transmissionGroups": [{"entries": [valid]}]},
                {"channelId": "nrk3", "hasPublicEpg": False, "transmissionGroups": [{"entries": [valid]}]},
            ])
        with patch.object(self.store, "_fetch_html", side_effect=fetch):
            rows = self.store._fetch_official_programs("no_nrk3", provider)
        self.assertEqual([row["title"] for row in rows], ["NRK 3 evening"] * 3)

    def test_nrk_actual_times_only_replace_already_started_programmes(self):
        provider = app.COUNTRIES["no"]["providers"]["no_nrk1"]
        now = datetime.now(app.EPG_TIMEZONE)
        past = now.replace(hour=0, minute=0, second=0, microsecond=0)
        future = (now + timedelta(days=1)).replace(hour=12)
        def item(title, start):
            return {"title": title, "start": {"planned": start.isoformat(), "actual": (start + timedelta(minutes=2)).isoformat()},
                    "end": {"planned": (start + timedelta(hours=1)).isoformat(), "actual": (start + timedelta(hours=1, minutes=2)).isoformat()}}
        data = [{"channelId": "nrk1", "hasPublicEpg": True,
                 "transmissionGroups": [{"entries": [item("Past", past), item("Future", future)]}]}]
        with patch.object(self.store, "_fetch_html", return_value=json.dumps(data)):
            rows = self.store._fetch_official_programs("no_nrk1", provider)
        by_title = {row["title"]: datetime.fromisoformat(row["start"]) for row in rows}
        self.assertEqual(by_title["Past"], past + timedelta(minutes=2))
        self.assertEqual(by_title["Future"], future)

    def test_secondary_guide_is_not_mislabelled_as_channel_owner(self):
        now = datetime.now(app.EPG_TIMEZONE)
        def fetch(channel, provider):
            return [{"title": channel, "start": now.isoformat(), "end": (now + timedelta(hours=1)).isoformat(),
                     "_source_url": provider["url"]}]
        with patch.object(self.store, "_fetch_official_programs", side_effect=fetch), \
                patch.object(self.store, "_fetch_teletext_programs", return_value=[]), \
                patch.object(self.store, "_fetch_secondary_web_programs", return_value=[]):
            self.store._supplement_missing_channels(self.store.channels)
        by_id = {channel["id"]: channel for channel in self.store.channels}
        for channel_id in app.base_channel_ids(self.store):
            row = by_id[channel_id]["programs"][0]
            direct = channel_id in app.COUNTRIES["no"]["providers"]
            self.assertEqual(row["_source_kind"], "broadcaster" if direct else "secondary-web")
            self.assertEqual(row["_source_rank"], 450 if direct else 300)
        self.assertEqual(self.store.official_metrics["enriched"], 20)


if __name__ == "__main__":
    unittest.main()
