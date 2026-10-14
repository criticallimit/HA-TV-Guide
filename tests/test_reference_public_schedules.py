"""Channel identity, real boundaries and failure isolation for public schedules."""

import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parents[1]
from reference_support import app


class PublicScheduleTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        paths = patch.multiple(app, OPTIONS_FILE=root / "options.json", CACHE_FILE=root / "feed.xml.gz",
                               PARSED_CACHE_FILE=root / "parsed.json", CHANNEL_PREFS_FILE=root / "order.json")
        paths.start()
        self.addCleanup(paths.stop)

    def test_dr_uses_numeric_station_id_and_explicit_end_across_midnight(self):
        store = app.EPGStore("dk")
        page = json.dumps([{"channelId": "DR1", "schedules": [{"item": {"title": "Wrong variant"}}]},
                           {"channelId": "20875", "schedules": [
                               {"startDate": "2026-10-06T21:30:00Z", "endDate": "2026-10-06T23:20:00Z",
                                "item": {"title": "The Guest (3:4)", "description": "Thrillerserie"}},
                               {"item": "Invalid"}]}])
        rows = store._parse_public_schedule(page, {"kind": "dr", "marker": "20875"})
        self.assertEqual([row["title"] for row in rows], ["The Guest (3:4)"])
        self.assertEqual(rows[0]["end_dt"].astimezone(app.EPG_TIMEZONE).date(), date(2026, 10, 7))

    def test_tv2_timestamps_are_seconds_and_other_danish_channels_are_not_mixed(self):
        store = app.EPGStore("dk")
        page = json.dumps([{"id": "3", "programs": [{"title": "TV 2 Nyheder", "start": 1791260400, "stop": 1791262800}]},
                           {"id": "133", "programs": [{"title": "TV 2 News", "start": 1791260400, "stop": 1791262800}]}])
        rows = store._parse_public_schedule(page, {"kind": "tv2dk", "marker": "3"})
        self.assertEqual([row["title"] for row in rows], ["TV 2 Nyheder"])
        self.assertEqual(rows[0]["start_dt"].year, 2026)
        self.assertEqual((rows[0]["end_dt"] - rows[0]["start_dt"]).total_seconds(), 2400)

    def test_rtbf_uses_current_tipik_id_not_old_channel_and_keeps_duration(self):
        store = app.EPGStore("be")
        row = {"channel": {"id": 33}, "title": "Ici tout commence", "scheduledAt": "2026-10-06T23:50:00+02:00", "duration": 2400}
        page = json.dumps({"status": 200, "data": [row, {**row, "channel": {"id": 6}, "title": "Old channel"},
                                                   {**row, "channel": "Malformed"}, {**row, "duration": None}]})
        rows = store._parse_public_schedule(page, {"kind": "rtbf", "marker": "33"})
        self.assertEqual([row["title"] for row in rows], ["Ici tout commence"])
        self.assertEqual(rows[0]["end_dt"].isoformat(), "2026-10-07T00:30:00+02:00")
        self.assertEqual(store._parse_public_schedule('{"status": 503, "data": []}', {"kind": "rtbf", "marker": "33"}), [])

    def test_danish_api_window_covers_local_day_on_both_dst_transitions(self):
        store = app.EPGStore("dk")
        provider = {"kind": "dr", "url": "https://example.test/schedules", "channels": ["20875", "20876"]}
        for day, expected_date, hour, duration in [(date(2026, 3, 29), "2026-03-28", "23", "23"),
                                                   (date(2026, 10, 25), "2026-10-24", "22", "25")]:
            params = parse_qs(urlparse(store._public_schedule_url(provider, day)).query)
            self.assertEqual((params["date"][0], params["hour"][0], params["duration"][0]), (expected_date, hour, duration))
            self.assertEqual(params["channels"], ["20875,20876"])

    def test_rtbf_window_uses_local_midnight_instead_of_utc_midnight(self):
        store = app.EPGStore("be")
        provider = {"kind": "rtbf", "url": "https://example.test/schedulings", "channels": ["1", "33", "3"]}
        params = parse_qs(urlparse(store._public_schedule_url(provider, date(2026, 10, 6))).query)
        self.assertEqual(params["scheduledAfter"], ["2026-10-05T22:00:00+00:00"])
        self.assertEqual(params["scheduledBefore"], ["2026-10-06T22:00:00+00:00"])

    def test_tvgids_keeps_column_identity_and_does_not_guess_missing_end(self):
        store = app.EPGStore("nl")
        page = '''<a class="guide__channel-container" href="/gids/rtl4">RTL 4</a>
        <a class="guide__channel-container" href="/gids/sbs6">SBS6</a>
        <div class="guide__hour-col" data-chidx="1"><div data-episode="1" class="program program--guide">
          <h3 class="program__title">RTL &amp; Show</h3><p class="program__text">Description <b>text</b></p>
          <span class="program__progress" data-start="1791260400" data-eind="1791262800"></span></div>
          <div data-episode="2" class="program program--guide"><h3 class="program__title">No end</h3>
          <span class="program__progress" data-start="1791262800"></span></div></div>
        <div class="guide__hour-col" data-chidx="2"><div data-episode="3" class="program program--guide">
          <h3 class="program__title">Other station</h3>
          <span class="program__progress" data-start="1791260400" data-eind="1791262800"></span></div></div>'''
        rows = store._parse_public_schedule(page, {"kind": "tvgids", "marker": "rtl4"})
        self.assertEqual([row["title"] for row in rows], ["RTL & Show"])
        self.assertEqual(rows[0]["desc"], "Description text")
        self.assertEqual(store._parse_public_schedule(page, {"kind": "tvgids", "marker": "rtl"}), [])

    def test_tvgids_today_uses_undated_route_and_other_days_use_exact_date(self):
        store = app.EPGStore("nl")
        provider = {"kind": "tvgids", "url": "https://www.tvgids.nl/gids/{date}/rtl4-rtl5"}
        today = datetime.now(app.EPG_TIMEZONE).date()
        self.assertEqual(store._public_schedule_url(provider, today), "https://www.tvgids.nl/gids/rtl4-rtl5")
        self.assertIn((today + timedelta(days=1)).strftime("%d-%m-%Y"), store._public_schedule_url(provider, today + timedelta(days=1)))

    def test_one_failed_day_retains_other_days_and_rejects_stale_naive_and_reversed_rows(self):
        store = app.EPGStore("dk")
        today = datetime.now(app.EPG_TIMEZONE).date()
        def fetch(url, label):
            if f"/{today.year}-{today.month}-{today.day}?" in url:
                raise OSError("Outage")
            return "{}"
        def parse(page, provider):
            start = datetime.combine(today + timedelta(days=1), datetime.min.time()).replace(tzinfo=app.EPG_TIMEZONE)
            return [{"title": "Valid", "start_dt": start, "end_dt": start + timedelta(hours=1)},
                    {"title": "Naive", "start_dt": start.replace(tzinfo=None), "end_dt": start.replace(tzinfo=None) + timedelta(hours=1)},
                    {"title": "Reversed", "start_dt": start, "end_dt": start - timedelta(hours=1)},
                    {"title": "Stale", "start_dt": start - timedelta(days=30), "end_dt": start - timedelta(days=30, hours=-1)}]
        provider = {"kind": "tv2dk", "marker": "3", "channels": ["3"], "url": "https://example.test"}
        with patch.object(store, "_fetch_html", side_effect=fetch), patch.object(store, "_parse_public_schedule", side_effect=parse):
            self.assertEqual([row["title"] for row in store._fetch_public_programs(provider)], ["Valid"])

    def test_joyn_key_rotation_at_headers_and_large_epg_limit(self):
        store = app.EPGStore("at")
        start = datetime.now(timezone.utc).timestamp()
        calls = []
        def fetch(url, label, headers=None):
            calls.append((url, headers))
            if url.endswith("/play/live-tv"):
                return '<script src="/_next/static/chunks/5563-new-hash.js"></script>'
            if url.endswith(".js"):
                return 'API_GW_API_KEY:{value:"rotated-public-client-key"}'
            event = {"startDate": start, "endDate": start + 3600, "program": {"title": "Austria"}}
            return json.dumps({"data": {"liveStreams": [{"id": "sat1-de", "epgEvents": [{**event, "program": {"title": "Germany"}}]},
                                                       {"id": "sat1-at", "epgEvents": [event]}]}})
        provider = {"kind": "joynat", "marker": "sat1-at", "url": "https://www.joyn.at/play/live-tv"}
        with patch.object(store, "_fetch_html", side_effect=fetch):
            rows = store._fetch_public_programs(provider)
        self.assertEqual([row["title"] for row in rows], ["Austria"])
        self.assertEqual(calls[-1][1]["Joyn-Country"], "AT")
        self.assertEqual(calls[-1][1]["Joyn-Distribution-Tenant"], "JOYN_AT")
        self.assertEqual(calls[-1][1]["x-api-key"], "rotated-public-client-key")
        self.assertIn("first: 500", parse_qs(urlparse(calls[-1][0]).query)["query"][0])
        self.assertNotIn("rotated-public-client-key", json.dumps(rows))

    def test_joyn_missing_client_config_and_graphql_errors_return_no_fake_schedule(self):
        store = app.EPGStore("at")
        provider = {"kind": "joynat", "marker": "atv", "url": "https://www.joyn.at/play/live-tv"}
        with patch.object(store, "_fetch_html", return_value="<html>No client config</html>"):
            self.assertEqual(store._fetch_public_programs(provider), [])
        with patch.object(store, "_fetch_html", side_effect=[
                '<script src="/5563-current.js"></script>', 'API_GW_API_KEY:{value:"public-key"}',
                '{"errors":[{"message":"Unavailable"}],"data":null}']):
            self.assertEqual(store._fetch_public_programs(provider), [])

    def test_shared_joyn_fetches_once_and_real_request_carries_austrian_headers(self):
        store = app.EPGStore("at")
        store._official_html_cache = {}
        store._official_fetch_errors = {}
        start = datetime.now(timezone.utc).timestamp()
        event = {"startDate": start, "endDate": start + 3600, "program": {"title": "Live show"}}
        payload = json.dumps({"data": {"liveStreams": [{"id": "atv", "epgEvents": [event]},
                                                       {"id": "atv2", "epgEvents": [event]}]}})
        calls = []
        def urlopen(request, timeout):
            calls.append(request)
            if request.full_url.endswith("/play/live-tv"):
                text = '<script src="/5563-live.js"></script>'
            elif request.full_url.endswith(".js"):
                text = 'API_GW_API_KEY:{value:"public-browser-key"}'
            else:
                text = payload
            response = BytesIO(text.encode())
            response.headers = Message()
            response.headers["Content-Type"] = "application/json; charset=utf-8"
            return response
        with patch.object(app, "urlopen", side_effect=urlopen):
            for marker in ["atv", "atv2"]:
                rows = store._fetch_public_programs({"kind": "joynat", "marker": marker, "url": "https://www.joyn.at/play/live-tv"})
                self.assertEqual(len(rows), 1)
        self.assertEqual(len(calls), 3)
        headers = {name.lower(): value for name, value in calls[-1].header_items()}
        self.assertEqual(headers["joyn-country"], "AT")
        self.assertEqual(headers["joyn-distribution-tenant"], "JOYN_AT")
        self.assertEqual(headers["x-api-key"], "public-browser-key")


if __name__ == "__main__":
    unittest.main()
