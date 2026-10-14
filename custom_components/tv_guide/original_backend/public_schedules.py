"""Public dated schedules for existing Danish, Austrian, Belgian and Dutch channels."""

import html
import json
import re
from datetime import timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo


class TVGidsScheduleParser(HTMLParser):
    """Use explicit epoch boundaries, never infer an end from the next title."""

    def __init__(self, channels):
        super().__init__(convert_charrefs=True)
        self.channels = channels
        self.stack = []
        self.programme = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        channel = self.stack[-1][1] if self.stack else None
        field = self.stack[-1][2] if self.stack else None
        if "guide__hour-col" in classes:
            channel = self.channels.get(attrs.get("data-chidx"))
        if tag == "div" and "data-episode" in attrs and "program--guide" in classes:
            self.programme = {"channel": channel, "title": "", "desc": "", "depth": len(self.stack)}
        if "program__title" in classes:
            field = "title"
        elif "program__text" in classes:
            field = "desc"
        if self.programme is not None and "program__progress" in classes:
            self.programme.update(start=attrs.get("data-start"), end=attrs.get("data-eind"))
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, channel, field))

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None)
        if index is None:
            return
        del self.stack[index:]
        if self.programme is not None and len(self.stack) <= self.programme["depth"]:
            self.rows.append(self.programme)
            self.programme = None

    def handle_data(self, data):
        if self.programme is not None and self.stack and self.stack[-1][2]:
            self.programme[self.stack[-1][2]] += data


class PublicProgrammeSources:
    def _public_schedule_url(self, provider, day):
        kind = provider["kind"]
        if kind == "tv2dk":
            return provider["url"] + f"/{day.year}-{day.month}-{day.day}?" + urlencode(
                [("ch", marker) for marker in provider["channels"]])
        if kind == "tvgids":
            if day == self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).date():
                return provider["url"].replace("{date}/", "")
            return provider["url"].format(date=day.strftime("%d-%m-%Y"))
        zone = ZoneInfo(self.runtime.COUNTRIES[self.country]["timezone"])
        start = self.runtime.datetime.combine(day, self.runtime.datetime.min.time()).replace(tzinfo=zone)
        end = self.runtime.datetime.combine(day + timedelta(days=1), self.runtime.datetime.min.time()).replace(tzinfo=zone)
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        if kind == "dr":
            params = {"channels": ",".join(provider["channels"]), "date": start.date().isoformat(),
                      "hour": start.hour, "duration": int((end - start).total_seconds() // 3600), "intersect": "true"}
        else:
            params = {"scheduledAfter": start.isoformat(), "scheduledBefore": end.isoformat(),
                      "channelIds": ",".join(provider["channels"]), "_limit": 500, "platform": "WEB"}
        return provider["url"] + "?" + urlencode(params)

    def _parse_public_schedule(self, page, provider):
        kind, marker = provider["kind"], provider["marker"]
        rows = []
        if kind == "tvgids":
            stations = re.findall(r'<a\b[^>]*class="[^"]*\bguide__channel-container\b[^"]*"[^>]*href="/gids/([^"/]+)"', page)
            parser = TVGidsScheduleParser({str(i + 1): station for i, station in enumerate(stations)})
            parser.feed(page)
            rows = [row for row in parser.rows if row["channel"] == marker]
        else:
            data = json.loads(page)
            if kind == "rtbf":
                if not isinstance(data, dict) or data.get("status") != 200:
                    return []
                rows = [row for row in data.get("data", []) if isinstance(row, dict)
                        and isinstance(row.get("channel"), dict) and str(row["channel"].get("id")) == marker]
            elif isinstance(data, list):
                for station in data:
                    if not isinstance(station, dict):
                        continue
                    key = "channelId" if kind == "dr" else "id"
                    if str(station.get(key)) == marker:
                        rows.extend(station.get("schedules" if kind == "dr" else "programs") or [])
        result = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                if kind == "dr":
                    item = row.get("item") or {}
                    if not isinstance(item, dict):
                        continue
                    title, desc = item.get("title"), item.get("description", "")
                    start = self.runtime.datetime.fromisoformat(row["startDate"])
                    end = self.runtime.datetime.fromisoformat(row["endDate"])
                elif kind == "rtbf":
                    title, desc = row.get("title"), row.get("description", "")
                    start = self.runtime.datetime.fromisoformat(row["scheduledAt"])
                    end = start + timedelta(seconds=float(row["duration"]))
                else:
                    title, desc = row.get("title"), row.get("desc", "")
                    start = self.runtime.datetime.fromtimestamp(float(row["start"]), timezone.utc)
                    end = self.runtime.datetime.fromtimestamp(float(row["end" if kind == "tvgids" else "stop"]), timezone.utc)
                result.append({"title": title, "desc": desc, "start_dt": start, "end_dt": end})
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
        return result

    def _fetch_joyn_at_schedule(self, provider, today):
        # Read the public web client's key on each refresh so rotations do not
        # require a new add-on version. This is not a user account credential.
        page = self._fetch_html(provider["url"], "Joyn Österreich")
        bundle = re.search(r'<script\b[^>]*src="([^"\s]*/5563-[^"\s]+\.js)"', page)
        if not bundle:
            return []
        script = self._fetch_html(urljoin(provider["url"], html.unescape(bundle[1])), "Joyn Web-Konfiguration")
        key = re.search(r'API_GW_API_KEY:\{value:"([^"]+)"', script)
        if not key:
            return []
        zone = ZoneInfo("Europe/Vienna")
        start = self.runtime.datetime.combine(today - timedelta(days=1), self.runtime.datetime.min.time()).replace(tzinfo=zone)
        end = self.runtime.datetime.combine(today + timedelta(days=3), self.runtime.datetime.min.time()).replace(tzinfo=zone)
        query = ("query LiveChannelsAndEpg($from: Timestamp, $to: Timestamp) { liveStreams(first: 500, offset: 0) "
                 "{ id title epgEvents(from: $from, to: $to, first: 500) { startDate endDate program "
                 "{ ... on EpgEntry { title } } } } }")
        url = "https://api.joyn.de/graphql?" + urlencode({"query": query, "variables": json.dumps(
            {"from": int(start.timestamp()), "to": int(end.timestamp())}, separators=(",", ":"))})
        data = json.loads(self._fetch_html(url, "Joyn Österreich EPG", headers={
            "x-api-key": key[1], "Joyn-Platform": "web", "Joyn-Country": "AT", "Joyn-Distribution-Tenant": "JOYN_AT"}))
        if not isinstance(data, dict) or data.get("errors"):
            return []
        result = []
        payload = data.get("data")
        if not isinstance(payload, dict):
            return []
        for station in payload.get("liveStreams") or []:
            if not isinstance(station, dict) or station.get("id") != provider["marker"]:
                continue
            for row in station.get("epgEvents") or []:
                if not isinstance(row, dict) or not isinstance(row.get("program"), dict):
                    continue
                try:
                    result.append({"title": (row.get("program") or {}).get("title"), "desc": "",
                                   "start_dt": self.runtime.datetime.fromtimestamp(float(row["startDate"]), timezone.utc),
                                   "end_dt": self.runtime.datetime.fromtimestamp(float(row["endDate"]), timezone.utc)})
                except (KeyError, TypeError, ValueError, OverflowError, OSError):
                    continue
        return url, result

    def _fetch_public_programs(self, provider):
        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)
        today = now.date()
        programmes = []
        offsets = [0] if provider["kind"] == "joynat" else range(-1, 3)
        for offset in offsets:
            day = today + timedelta(days=offset)
            try:
                if provider["kind"] == "joynat":
                    fetched = self._fetch_joyn_at_schedule(provider, today)
                    if not fetched:
                        continue
                    url, rows = fetched
                else:
                    url = self._public_schedule_url(provider, day)
                    rows = self._parse_public_schedule(self._fetch_html(url, provider["kind"]), provider)
                for row in rows:
                    start, end = row["start_dt"], row["end_dt"]
                    if (not isinstance(row.get("title"), str) or not row["title"].strip()
                            or start.utcoffset() is None or end.utcoffset() is None
                            or not 0 < end.timestamp() - start.timestamp() <= 86400):
                        continue
                    start, end = start.astimezone(self.runtime.EPG_TIMEZONE), end.astimezone(self.runtime.EPG_TIMEZONE)
                    if provider["kind"] != "joynat" and not day - timedelta(days=1) <= start.date() <= day + timedelta(days=1):
                        continue
                    if end <= now - timedelta(hours=6) or not today - timedelta(days=1) <= start.date() < today + timedelta(days=3):
                        continue
                    programmes.append({"title": row["title"].strip(), "subtitle": "", "desc": row.get("desc") or "",
                                       "category": "", "icon": None, "start": start.isoformat(), "end": end.isoformat(),
                                       "_source_url": url.split("?", 1)[0] if provider["kind"] == "joynat" else url})
            except (KeyError, TypeError, ValueError, OSError) as exc:
                print(f"[TV Guide] Senderquelle {provider['kind']} für {day}: {exc}", flush=True)
        return self._merge_program_lists([], programmes)
