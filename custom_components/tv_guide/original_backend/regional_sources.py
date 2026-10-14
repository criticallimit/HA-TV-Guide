"""Dated broadcaster schedules for existing Swedish and Swiss channels."""

import html
import json
import re
from datetime import timedelta


class RegionalProgrammeSources:
    def _parse_tv4_schedule(self, page, marker, day):
        match = re.search(r'<script\b[^>]*\bid=[\"\']__NEXT_DATA__[\"\'][^>]*>(.*?)</script>', page, re.S)
        if not match:
            return []
        state = json.loads(match[1]).get("props", {}).get("apolloState", {})

        def resolve(value):
            if not isinstance(value, dict):
                return {}
            return state.get(value["__ref"], {}) if "__ref" in value else value

        schedules = []
        for key, value in state.get("ROOT_QUERY", {}).items():
            if key.startswith("schedule(") and json.loads(key[len("schedule("):-1]).get("date") == day.isoformat():
                schedules.extend(value)
        result = []
        for ref in schedules:
            station = resolve(ref)
            if station.get("name") != marker or station.get("day") != day.isoformat():
                continue
            for broadcast in station.get("broadcasts", []):
                item = resolve(broadcast)
                synopsis = resolve(item.get("synopsis"))
                try:
                    result.append({
                        "title": item["title"],
                        "desc": next((synopsis[key] for key in ("long", "medium", "short", "brief") if synopsis.get(key)), ""),
                        "start_dt": self.runtime.datetime.fromisoformat(item["start"]),
                        "end_dt": self.runtime.datetime.fromisoformat(item["end"]),
                    })
                except (KeyError, TypeError, ValueError):
                    continue
        return result

    def _parse_chmedia_schedule(self, page, marker, day):
        if day.isoformat() not in re.findall(r'\bdata-epg-date=[\"\']([^\"\']+)[\"\']', page):
            return []
        result = []
        for row in re.split(r'<div\b[^>]*class="epg2__row"[^>]*>', page)[1:]:
            station = re.search(r'<a\b[^>]*class="epg2__ch"[^>]*href="/sender/([^\"]+)"', row)
            if not station or station[1] != marker:
                continue
            for attrs, content in re.findall(r'<div\b([^>]*\bdata-epg2-prog\b[^>]*)>(.*?)</div>', row, re.S):
                attributes = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
                title = re.search(r'<span\b[^>]*class="epg2__prog-title"[^>]*>(.*?)</span>', content, re.S)
                if not title:
                    continue
                try:
                    result.append({
                        "title": html.unescape(re.sub(r"<[^>]+>", "", title[1])).strip(),
                        "start_dt": self.runtime.datetime.fromisoformat(attributes["data-start"]),
                        "end_dt": self.runtime.datetime.fromisoformat(attributes["data-end"]),
                    })
                except (KeyError, TypeError, ValueError):
                    continue
        return result

    def _fetch_regional_programs(self, provider):
        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)
        today = now.date()
        programmes = []
        parser = self._parse_tv4_schedule if provider["kind"] == "tv4" else self._parse_chmedia_schedule
        # Yesterday's final programme may still be on air after midnight.
        for offset in range(-1, 3):
            day = today + timedelta(days=offset)
            date = day.strftime("%Y/%m/%d") if provider["kind"] == "chmedia" else day.isoformat()
            url = provider["url"].format(date=date)
            try:
                rows = parser(self._fetch_html(url, provider["kind"]), provider["marker"], day)
                for item in rows:
                    start, end = item["start_dt"], item["end_dt"]
                    if (not item.get("title") or start.utcoffset() is None or end.utcoffset() is None
                            or not start < end <= start + timedelta(days=1)):
                        continue
                    start, end = start.astimezone(self.runtime.EPG_TIMEZONE), end.astimezone(self.runtime.EPG_TIMEZONE)
                    if not day <= start.date() <= day + timedelta(days=1):
                        continue
                    if end <= now - timedelta(hours=6) or start.date() >= today + timedelta(days=3):
                        continue
                    programmes.append({
                        "title": item["title"], "subtitle": "", "desc": item.get("desc", ""),
                        "category": "", "icon": None, "start": start.isoformat(), "end": end.isoformat(),
                        "_source_url": url,
                    })
            except (KeyError, TypeError, ValueError, OSError) as exc:
                print(f"[TV Guide] Senderquelle {provider['kind']} für {day}: {exc}", flush=True)
        return self._merge_program_lists([], programmes)
