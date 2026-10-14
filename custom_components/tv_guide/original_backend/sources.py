"""XMLTV and public broadcaster schedule parsers.


The application context is supplied by services.py; all mutable state is shared.
"""

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from urllib.parse import urlparse
from urllib.request import Request
from zoneinfo import ZoneInfo


class ProgrammeSources:
    OFFICIAL_PROVIDER_HANDLERS = {
        "fr_m6": ("_fetch_french_programs", "provider"),
        "fr_tf1": ("_fetch_french_programs", "provider"),
        "fr_ftv": ("_fetch_french_programs", "provider"),
        "fr_arte": ("_fetch_french_programs", "provider"),
        "srg": ("_fetch_country_official_programs", "provider"),
        "orf": ("_fetch_country_official_programs", "provider"),
        "play": ("_fetch_country_official_programs", "provider"),
        "npo": ("_fetch_country_official_programs", "provider"),
        "vrt": ("_fetch_country_official_programs", "provider"),
        "vtm": ("_fetch_country_official_programs", "provider"),
        "nrk": ("_fetch_country_official_programs", "provider"),
        "tv2no": ("_fetch_country_official_programs", "provider"),
        "svt": ("_fetch_country_official_programs", "provider"),
        "tv4": ("_fetch_regional_programs", "provider"),
        "chmedia": ("_fetch_regional_programs", "provider"),
        "dr": ("_fetch_public_programs", "provider"),
        "tv2dk": ("_fetch_public_programs", "provider"),
        "rtbf": ("_fetch_public_programs", "provider"),
        "joynat": ("_fetch_public_programs", "provider"),
        "tvgids": ("_fetch_public_programs", "provider"),
        "radiobremen": ("_fetch_radio_bremen_programs", "none"),
        "swr": ("_fetch_swr_programs", "none"),
        "sr": ("_fetch_sr_programs", "none"),
    }
    def _xml_records(self, tag):
        """Yield complete root children and release them, including skipped tags."""
        with self._open_xml() as fh:
            root = None
            depth = 0
            for event, elem in ET.iterparse(fh, events=("start", "end")):
                if event == "start":
                    depth += 1
                    if root is None:
                        root = elem
                else:
                    if depth == 2:
                        try:
                            if elem.tag == tag:
                                yield elem
                        finally:
                            elem.clear()
                            root.remove(elem)
                    depth -= 1

    def _build_channel_map(self):
        exact_ids = {}
        literal_ids = {}
        exact_names = {}
        shared_source_ids = {}
        configured_by_id = {ch["id"]: ch for ch in self.catalog["channels"]}

        for ch in self.catalog["channels"]:
            internal_id = ch["id"]

            for value in ch.get("xmltv_ids", []):
                if ch.get("xmltv_id_exact"):
                    literal_ids.setdefault(value, []).append(internal_id)
                    continue
                key = self.runtime.normalize(value)
                if key:
                    exact_ids.setdefault(key, []).append(internal_id)

            names = [] if ch.get("xmltv_id_only") else [ch["name"], ch["id"], *ch.get("aliases", [])]
            for value in names:
                key = self.runtime.normalize(value)
                if key:
                    exact_names.setdefault(key, []).append(internal_id)

            for source_id in ch.get("shared_xmltv_ids", []):
                shared_source_ids.setdefault(source_id, []).append(internal_id)

        channel_meta = {}
        claimed_source_ids = set()

        for elem in self._xml_records("channel"):

            cid = elem.attrib.get("id", "")
            if cid in self.runtime.COUNTRIES[self.country].get("excluded_xmltv_ids", []):
                elem.clear()
                continue
            names = [(x.text or "").strip() for x in elem.findall("display-name") if x.text]
            icon = elem.find("icon")
            icon_url = icon.attrib.get("src") if icon is not None else None
            display_name = names[0] if names else cid

            if cid in shared_source_ids:
                for internal_id in shared_source_ids[cid]:
                    channel_meta[internal_id] = {
                        "xmltv_id": cid,
                        "display_name": display_name,
                        "icon": icon_url,
                        "configured": True,
                    }
                claimed_source_ids.add(cid)
                elem.clear()
                continue

            cid_key = self.runtime.normalize(cid)
            name_keys = [self.runtime.normalize(name) for name in names if self.runtime.normalize(name)]
            candidates = list(literal_ids.get(cid, []))

            if cid_key in exact_ids:
                candidates.extend(exact_ids[cid_key])

            if not candidates:
                for key in name_keys:
                    candidates.extend(exact_names.get(key, []))

            if not candidates:
                source_keys = [cid_key, *name_keys]
                fuzzy = set()
                for skey in source_keys:
                    if len(skey) < 7:
                        continue
                    for known_key, internal_ids in exact_names.items():
                        if len(known_key) < 7:
                            continue
                        if skey.startswith(known_key) or known_key.startswith(skey):
                            fuzzy.update(internal_ids)
                if len(fuzzy) == 1:
                    candidates = list(fuzzy)

            unique = list(dict.fromkeys(candidates))
            if len(unique) == 1 and cid not in claimed_source_ids:
                internal_id = unique[0]
                if internal_id not in channel_meta:
                    channel_meta[internal_id] = {
                        "xmltv_id": cid,
                        "display_name": display_name,
                        "icon": icon_url,
                        "configured": True,
                    }
                    claimed_source_ids.add(cid)
                    elem.clear()
                    continue

            # Every unmatched XMLTV channel is still part of the catalogue.
            # The source id is hashed only for the stable internal key; the
            # original XMLTV id remains available as source_id.
            source_identity = cid if self.country == "de" else f"{self.country}:{cid}"
            dynamic_base_id = self.runtime.feed_channel_id(source_identity)
            dynamic_id = dynamic_base_id
            suffix = 1
            while dynamic_id in channel_meta or dynamic_id in configured_by_id:
                dynamic_id = f"{dynamic_base_id}_{suffix}"
                suffix += 1

            channel_meta[dynamic_id] = {
                "xmltv_id": cid,
                "display_name": display_name,
                "icon": icon_url,
                "configured": False,
            }
            claimed_source_ids.add(cid)
            elem.clear()

        return channel_meta

    def _parse(self):
        channel_meta = self._build_channel_map()
        configured_by_id = {ch["id"]: ch for ch in self.catalog["channels"]}

        xml_to_internal = {}
        for internal_id, meta in channel_meta.items():
            xml_to_internal.setdefault(meta["xmltv_id"], []).append(internal_id)

        programmes = {internal_id: [] for internal_id in channel_meta}
        seen_programmes = 0
        matched_programmes = 0
        first_start = None
        last_start = None
        latest_end = None

        for elem in self._xml_records("programme"):
            seen_programmes += 1
            source_id = elem.attrib.get("channel", "")
            internal_ids = xml_to_internal.get(source_id, [])
            if not internal_ids:
                elem.clear()
                continue

            start = self.runtime.xmltv_datetime(elem.attrib.get("start"))
            end = self.runtime.xmltv_datetime(elem.attrib.get("stop"))
            if not start or not end or end.timestamp() <= start.timestamp():
                elem.clear()
                continue

            # Compare instants: a repeated wall-clock hour at the autumn DST
            # transition can have an earlier-looking end but positive duration.
            first_start = start if first_start is None or start.timestamp() < first_start.timestamp() else first_start
            last_start = start if last_start is None or start.timestamp() > last_start.timestamp() else last_start
            latest_end = end if latest_end is None or end.timestamp() > latest_end.timestamp() else latest_end

            icon = elem.find("icon")
            item = {
                "title": self.runtime.first_text(elem, "title") or "Ohne Titel",
                "subtitle": self.runtime.first_text(elem, "sub-title"),
                "desc": self.runtime.first_text(elem, "desc"),
                "category": self.runtime.first_text(elem, "category"),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "icon": icon.attrib.get("src") if icon is not None else None,
            }
            for internal_id in internal_ids:
                programmes[internal_id].append(dict(item))
                matched_programmes += 1
            elem.clear()

        self.feed_latest_end = latest_end.isoformat() if latest_end else None
        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)
        if latest_end and latest_end < now - timedelta(hours=2):
            raise ValueError(
                f"EPG-Feed ist veraltet: letzte Sendung endet am {latest_end.isoformat()}; "
                f"aktuelle Zeit ist {now.isoformat()}."
            )

        print(
            "[TV Guide] XMLTV Diagnose: "
            f"{len(channel_meta)} Sender im Feed-Katalog, "
            f"{seen_programmes} Programme im Feed, "
            f"{matched_programmes} Programme übernommen"
            + (f", Zeitraum {first_start.isoformat()} bis {last_start.isoformat()}" if first_start and last_start else ""),
            flush=True,
        )

        result = []
        dynamic_order = 10000
        for internal_id, meta in channel_meta.items():
            items = sorted(programmes.get(internal_id, []), key=lambda x: x["start"])
            configured = configured_by_id.get(internal_id)

            if configured:
                channel = {
                    **configured,
                    "preset": True,
                    "catalog_group": "Hauptsender",
                    "logo": meta.get("icon"),
                    "logo_light": configured.get("logo_file_light") or configured.get("logo_file"),
                    "logo_dark": configured.get("logo_file") or configured.get("logo_file_light"),
                }
            else:
                channel = {
                    "order": dynamic_order,
                    "id": internal_id,
                    "name": (meta.get("display_name") or meta.get("xmltv_id") or internal_id).removesuffix(f".{self.country}") if self.country != "de" else meta.get("display_name") or meta.get("xmltv_id") or internal_id,
                    "aliases": [],
                    "xmltv_ids": [meta.get("xmltv_id")],
                    "logo_file": None,
                    "logo_file_light": None,
                    "preset": False,
                    "catalog_group": "Weitere Sender",
                    "logo": meta.get("icon"),
                    # Most XMLTV providers expose one official logo. Keep
                    # separate theme fields so providers with two variants can
                    # be supported without changing the catalogue model.
                    "logo_light": meta.get("icon"),
                    "logo_dark": meta.get("icon"),
                }
                dynamic_order += 1

            channel.update({
                "source_name": meta.get("display_name"),
                "source_id": meta.get("xmltv_id"),
                "available": bool(items),
                "programs": items,
            })
            result.append(channel)

        # Keep the complete configured main-channel set stable even when the
        # current XMLTV feed temporarily omits one or more stations.
        existing_ids = {item["id"] for item in result}
        for configured in sorted(self.catalog["channels"], key=lambda x: x["order"]):
            if configured["id"] in existing_ids:
                continue
            result.append({
                **configured,
                "preset": True,
                "catalog_group": "Hauptsender",
                "logo": configured.get("logo_url"),
                "logo_light": configured.get("logo_file_light") or configured.get("logo_file") or configured.get("logo_url"),
                "logo_dark": configured.get("logo_file") or configured.get("logo_file_light") or configured.get("logo_url"),
                "source_name": None,
                "source_id": None,
                "available": False,
                "programs": [],
            })

        result.sort(key=lambda ch: (
            0 if ch.get("preset") else 1,
            ch.get("order", 99999) if ch.get("preset") else 99999,
            str(ch.get("name") or "").casefold(),
        ))
        return result

    def _clean_anchor_text(self, fragment):
        text = re.sub(r"<[^>]+>", " ", fragment)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _fetch_radio_bremen_programs(self):
        today = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).date()
        programmes = []
        for day_index in range(3):
            schedule_date = today + timedelta(days=day_index)
            page = self._fetch_html(
                self.runtime.ARD_RB_PROGRAM_URL.format(date=schedule_date.isoformat()), "Radio Bremen",
            )
            programmes.extend(self._parse_ard_programmes(page, "Radio Bremen", schedule_date))
        return self._merge_program_lists([], programmes)

    def _fetch_html(self, url, label, headers=None):
        cache = getattr(self, "_official_html_cache", None)
        if isinstance(cache, dict) and url in cache:
            return cache[url]
        failures = getattr(self, "_official_fetch_errors", None)
        if isinstance(failures, dict) and url in failures:
            raise OSError(failures[url])

        req = Request(
            url,
            headers={"Accept": "text/html"} if urlparse(url).hostname == "vtm.be" else {
                "User-Agent": "Mozilla/5.0 HomeAssistant-TV-Guide/1.0",
                "Accept": "application/vnd.nrk.epg.v2+json" if urlparse(url).hostname == "psapi.nrk.no" else "application/json" if urlparse(url).hostname in {"il.srgssr.ch", "tv2no-epg-api.public.tv2.no", "prod95-cdn.dr-massive.com", "tvtid-api.api.tv2.dk", "bff-service.rtbf.be", "api.joyn.de"} else "text/html,application/xhtml+xml",
                **(headers or {}),
            },
        )
        try:
            with self.runtime.urlopen(req, timeout=20) as response:
                page = response.read(8 * 1024 * 1024 + 1)
                if len(page) > 8 * 1024 * 1024:
                    raise ValueError(f"{label}-Programmseite ist unerwartet groß.")
                charset = response.headers.get_content_charset() or "utf-8"
                page = page.decode(charset, errors="replace")
        except (OSError, ValueError) as exc:
            if isinstance(failures, dict):
                failures[url] = str(exc)
            raise

        if isinstance(cache, dict):
            cache[url] = page
        return page

    def _build_programmes_from_starts(self, raw_items):
        unique = {}
        for item in raw_items:
            key = (item["start_dt"].isoformat(), item["title"])
            unique[key] = item

        ordered = sorted(unique.values(), key=lambda x: x["start_dt"])
        programmes = []
        for index, item in enumerate(ordered):
            start_dt = item["start_dt"]
            if item.get("end_dt"):
                end_dt = item["end_dt"]
            elif index + 1 < len(ordered):
                end_dt = ordered[index + 1]["start_dt"]
            else:
                end_dt = start_dt + timedelta(hours=1)

            if end_dt <= start_dt or end_dt - start_dt > timedelta(hours=6):
                end_dt = start_dt + timedelta(hours=1)

            programmes.append({
                "title": item["title"],
                "subtitle": item.get("subtitle", ""),
                "desc": item.get("desc", ""),
                "category": item.get("category", ""),
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "icon": item.get("icon"),
            })
        return programmes

    def _html_lines(self, page):
        page = re.sub(r"<!--.*?-->", " ", page, flags=re.S)
        page = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", page, flags=re.I | re.S)
        page = re.sub(
            r"</?(?:h[1-6]|p|div|li|article|section|br|tr|td|th|option|button)\b[^>]*>",
            "\n",
            page,
            flags=re.I,
        )
        page = html.unescape(re.sub(r"<[^>]+>", " ", page))
        lines = []
        for raw in page.splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if line:
                lines.append(line)
        return lines

    def _parse_schedule_lines(self, lines, schedule_date, max_programmes=100):
        raw_items = []
        previous_minutes = None
        day_offset = 0
        skip_indices = set()

        for index, line in enumerate(lines):
            if index in skip_indices:
                continue

            match = re.match(
                r"^(?:Seit\s+)?(\d{1,2})[:.](\d{2})(?![\d.])(?:\s*[-–]\s*\d{1,2}[:.]\d{2})?(?:\s+Uhr\b)?\s*(.*)$",
                line,
            )
            if not match:
                continue

            hour = int(match.group(1))
            minute = int(match.group(2))
            if hour > 23 or minute > 59:
                continue

            title = match.group(3).strip(" -–")

            # Some public programme pages render start time, end time and title
            # as three consecutive text lines. Treat the second time as the end
            # marker instead of a second programme.
            if not title and index + 2 < len(lines):
                next_time = re.match(r"^(\d{1,2})[:.](\d{2})$", lines[index + 1])
                following = lines[index + 2].strip()
                if next_time and following and not re.match(
                    r"^\d{1,2}[:.]\d{2}", following
                ):
                    title = following
                    skip_indices.add(index + 1)

            if not title and index + 1 < len(lines):
                title = lines[index + 1].strip()
            if not title or not re.search(r"[A-Za-zÄÖÜäöüß]", title) or re.fullmatch(r"\([AB]\)", title):
                continue
            if re.match(r"^\d{1,2}[:.]\d{2}", title) or self.runtime.normalize(title) in {
                "uhr", "jetzt", "heute", "morgen", "gestern", "nachts", "abends",
            } or re.search(r"\d{1,2}[:.]\d{2}\s*[-–]\s*\d{1,2}[:.]\d{2}", title):
                continue

            minutes = hour * 60 + minute
            if previous_minutes is not None and minutes + 360 < previous_minutes:
                day_offset += 1
            previous_minutes = minutes

            start_dt = self.runtime.datetime.combine(
                schedule_date + timedelta(days=day_offset),
                self.runtime.datetime.min.time(),
            ).replace(tzinfo=self.runtime.EPG_TIMEZONE).replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
            raw_items.append({
                "title": title,
                "subtitle": "",
                "desc": "",
                "category": "",
                "start_dt": start_dt,
                "icon": None,
            })
            if len(raw_items) >= max_programmes:
                break

        return self._build_programmes_from_starts(raw_items)

    def _provider_section(self, lines, channel_id, provider):
        kind = provider.get("kind")
        marker = str(provider.get("marker") or "").strip()
        if kind not in {"ard", "zdf"} or not marker:
            return lines

        family_markers = [
            str(item.get("marker") or "").strip()
            for item in self.runtime.OFFICIAL_PROVIDER_BY_CHANNEL.values()
            if item and item.get("kind") == kind and item.get("marker")
        ]

        start = None
        marker_key = self.runtime.normalize(marker)
        for index, line in enumerate(lines):
            line_key = self.runtime.normalize(line)
            if line_key == marker_key or line_key.startswith(marker_key):
                start = index + 1
                break

        if start is None and channel_id == "ard" and kind == "ard":
            start = next(
                (
                    index + 1
                    for index, line in enumerate(lines)
                    if self.runtime.normalize(line) == self.runtime.normalize("Programmübersicht")
                ),
                0,
            )

        if start is None:
            return []

        end = len(lines)
        other_keys = {
            self.runtime.normalize(value)
            for value in family_markers
            if self.runtime.normalize(value) != marker_key
        }
        for index in range(start, len(lines)):
            line_key = self.runtime.normalize(lines[index])
            if any(line_key == key or line_key.startswith(key) for key in other_keys):
                end = index
                break
        return lines[start:end]

    def _parse_ard_programmes(self, page, marker, schedule_date):
        """Read dated broadcasts for exactly one channel, never navigation text."""
        programmes = []

        def visit(value):
            if isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, dict):
                channel = value.get("channel") or {}
                if isinstance(channel, dict) and self.runtime.normalize(channel.get("name")) == self.runtime.normalize(marker):
                    try:
                        start = self.runtime.datetime.fromisoformat(value["broadcastedOn"])
                        end = self.runtime.datetime.fromisoformat(value["broadcastEnd"])
                        title = str(value.get("coreTitle") or value.get("title") or "").strip()
                        if title and start.utcoffset() is not None and end > start and start.date() == schedule_date:
                            programmes.append({
                                "title": title, "subtitle": value.get("coreSubline") or "",
                                "desc": value.get("synopsis") or "", "category": "",
                                "start": start.isoformat(), "end": end.isoformat(), "icon": None,
                            })
                    except (KeyError, TypeError, ValueError):
                        pass
                for child in value.values():
                    if isinstance(child, (list, dict)):
                        visit(child)

        for body in re.findall(r'<script\b[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', page, re.I | re.S):
            try:
                visit(json.loads(body))
            except (TypeError, ValueError):
                continue
        return self._merge_program_lists([], programmes)

    def _page_matches_date(self, lines, schedule_date):
        # The first explicit full date is the page's date, not a requested URL.
        for line in lines:
            match = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", line)
            if match:
                try:
                    return self.runtime.datetime(int(match[3]), int(match[2]), int(match[1])).date() == schedule_date
                except ValueError:
                    return False
        return False

    def _parse_rtl_programmes(self, page, channel_id, schedule_date):
        names = {"rtl": "RTL", "vox": "VOX", "nitro": "NITRO", "rtlup": "RTLup",
                 "voxup": "VOXup", "superrtl": "SUPER RTL"}
        marker = names.get(channel_id)
        if not marker:
            return []
        chunks = []
        for match in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', page):
            try:
                chunks.append(json.loads(match[1]))
            except ValueError:
                continue
        text = "".join(chunks)
        decoder = json.JSONDecoder()
        programmes = []

        def visit(value):
            if isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, dict):
                if (self.runtime.normalize(value.get("broadcastService")) == self.runtime.normalize(marker)
                        and value.get("type", "BroadcastEvent") == "BroadcastEvent"):
                    try:
                        start = self.runtime.datetime.fromisoformat(value["startDate"])
                        end = self.runtime.datetime.fromisoformat(value["endDate"])
                        if start.utcoffset() is not None and end.utcoffset() is not None:
                            start = start.astimezone(self.runtime.EPG_TIMEZONE)
                            end = end.astimezone(self.runtime.EPG_TIMEZONE)
                            works = value.get("workFeatured") or []
                            if isinstance(works, dict):
                                works = [works]
                            work = next((item for item in works if isinstance(item, dict)), {})
                            series = work.get("partOfSeries") or {}
                            series_title = series.get("name") if isinstance(series, dict) else ""
                            title = str(series_title or value.get("name") or value.get("alternateName") or work.get("name") or "").strip()
                            subtitle = (work.get("name") or value.get("alternateName") or value.get("name")) if series_title else (
                                value.get("alternateName") if value.get("name") else ""
                            )
                            subtitle = str(subtitle or "").strip()
                            if self.runtime.normalize(subtitle) == self.runtime.normalize(title):
                                subtitle = ""
                            if title and start.date() == schedule_date and end > start:
                                programmes.append({
                                    "title": title,
                                    "subtitle": subtitle,
                                    "desc": value.get("description") or "", "category": "",
                                    "start": start.isoformat(), "end": end.isoformat(), "icon": None,
                                })
                    except (KeyError, TypeError, ValueError):
                        pass
                for child in value.values():
                    if isinstance(child, (dict, list)):
                        visit(child)

        for match in re.finditer(r"(?:^|\n)[0-9a-f]+:([\[{])", text):
            try:
                visit(decoder.raw_decode(text, match.start(1))[0])
            except ValueError:
                continue
        return self._merge_program_lists([], programmes)

    def _teletext_matches_date(self, lines, schedule_date):
        if any(re.search(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", line) for line in lines):
            return self._page_matches_date(lines, schedule_date)
        weekdays = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
        months = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"]
        for line in lines:
            match = re.search(r"\b(" + "|".join(weekdays) + r"),?\s+(\d{1,2})\.\s*(" + "|".join(months) + r")\b", line, re.I)
            if match:
                return (weekdays.index(match[1].lower()) == schedule_date.weekday()
                        and int(match[2]) == schedule_date.day
                        and months.index(match[3].lower()) + 1 == schedule_date.month)
        return False

    def _fetch_generic_official_programs(self, channel_id, provider):
        today = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).date()
        url_template = provider.get("url")
        kind = provider.get("kind")

        if kind == "ard":
            url_template = self.runtime.ARD_PROGRAM_URL
        elif kind == "zdf":
            url_template = self.runtime.ZDF_PROGRAM_URL

        if not url_template:
            return []

        programmes = []
        day_count = 3 if "{date}" in url_template else 1
        for day_index in range(day_count):
            schedule_date = today + timedelta(days=day_index)
            url = url_template.format(date=schedule_date.isoformat())
            page = self._fetch_html(url, channel_id)
            if channel_id in {"rtl", "vox", "nitro", "rtlup", "voxup", "superrtl"}:
                programmes.extend(self._parse_rtl_programmes(page, channel_id, schedule_date))
                continue
            if kind == "ard":
                programmes.extend(self._parse_ard_programmes(page, provider.get("marker"), schedule_date))
                continue
            lines = self._html_lines(page)
            if not self._page_matches_date(lines, schedule_date):
                continue
            lines = self._provider_section(lines, channel_id, provider)
            if not lines:
                continue
            programmes.extend(
                self._parse_schedule_lines(
                    lines,
                    schedule_date,
                    max_programmes=120,
                )
            )

        by_start = {}
        for item in programmes:
            start = item.get("start")
            item.setdefault("_source_url", url_template.format(date=self.runtime.datetime.fromisoformat(start).astimezone(self.runtime.EPG_TIMEZONE).date().isoformat()) if start else url_template)
            if start and start not in by_start:
                by_start[start] = item
        return sorted(by_start.values(), key=lambda item: item.get("start") or "")

    def _clean_teletext_title(self, title):
        title = re.sub(r"\s+(?:Seite|S\.)\s*[1-9]\d{2}\s*$", "", title)
        # Page references accompanying accessibility codes are annotations,
        # while ordinary title numbers (e.g. a film year) remain untouched.
        return re.sub(
            r"(?:\s+(?:UT|AD|DGS)(?:\s*/\s*(?:UT|AD|DGS))*)+(?:\s+[1-9]\d{2})?\s*$",
            "", title,
        ).strip()

    def _teletext_lines(self, page):
        def remove_page_reference(match):
            attributes, content = match.groups()
            href = re.search(r'''\bhref\s*=\s*(["'])(.*?)\1''', attributes, re.I | re.S)
            if not href:
                return match[0]
            target = re.search(r"(?:^|/)([1-9]\d{2})(?:\.html?)?/?$", urlparse(html.unescape(href[2])).path)
            if not target:
                return match[0]
            text = self._clean_anchor_text(content)
            cleaned = re.sub(r"(?<!\w)" + target[1] + r"\s*$", "", text).strip()
            if cleaned == text:
                return match[0]
            return " " + html.escape(cleaned) + " "

        page = re.sub(r"<a\b([^>]*)>(.*?)</a>", remove_page_reference, page, flags=re.I | re.S)
        return self._html_lines(page)

    def _fetch_teletext_programs(self, channel_id):
        provider = self.runtime.TELETEXT_PROVIDER_BY_CHANNEL.get(channel_id)
        if not provider:
            return []

        today = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).date()
        programmes = []
        for day_key, date_offset in (("today", 0), ("tomorrow", 1)):
            schedule_date = today + timedelta(days=date_offset)
            for url in provider.get(day_key, []):
                try:
                    page = self._fetch_html(url, f"{channel_id} Videotext")
                    lines = self._teletext_lines(page)
                    if not self._teletext_matches_date(lines, schedule_date):
                        continue
                    parsed = self._parse_schedule_lines(lines, schedule_date, max_programmes=120)
                    for item in parsed:
                        item["title"] = self._clean_teletext_title(item["title"])
                        item["_source_url"] = url
                    programmes.extend(item for item in parsed if item["title"])
                except Exception as exc:
                    print(
                        f"[TV Guide] Videotext-Seite übersprungen für {channel_id}: "
                        f"{url} -> {exc}",
                        flush=True,
                    )

        by_start = {}
        for item in programmes:
            start = item.get("start")
            if not start:
                continue
            current = by_start.get(start)
            if current is None or self._programme_score(item) > self._programme_score(current):
                by_start[start] = item
        return sorted(by_start.values(), key=lambda item: item.get("start") or "")

    def _fetch_secondary_web_programs(self, channel_id):
        url_template = self.runtime.SECONDARY_WEB_PROVIDER_BY_CHANNEL.get(channel_id)
        if not url_template:
            return []

        today = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).date()
        programmes = []
        for day_index in range(3):
            schedule_date = today + timedelta(days=day_index)
            url = url_template.format(date=schedule_date.isoformat())
            page = self._fetch_html(url, f"{channel_id} Sekundärquelle")
            lines = self._html_lines(page)
            if not self._page_matches_date(lines, schedule_date):
                continue
            programmes.extend(
                self._parse_schedule_lines(
                    lines,
                    schedule_date,
                    max_programmes=140,
                )
            )
        return self._merge_program_lists([], programmes)

    def _fetch_public_schedule_json(self, url, query):
        cache = getattr(self, "_official_html_cache", None)
        key = (url, query)
        if isinstance(cache, dict) and key in cache:
            return json.loads(cache[key])
        request = Request(url, data=json.dumps({"query": query}).encode("utf-8"), headers={
            "Content-Type": "application/json", "X-VRT-CLIENT-NAME": "WEB",
            "User-Agent": "HomeAssistant-TV-Guide/1.0",
        })
        with self.runtime.urlopen(request, timeout=20) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Senderprogramm ist unerwartet groß.")
        text = data.decode("utf-8")
        result = json.loads(text)
        if result.get("errors"):
            raise ValueError("Senderprogramm konnte nicht vollständig gelesen werden.")
        if isinstance(cache, dict):
            cache[key] = text
        return result

    def _fetch_vrt_programmes(self, provider, day):
        page_id = f'/vrtmax/tv-gids/{provider["station"]}/{day.isoformat()}/'
        fields = 'title description indexMeta { value } statusMeta { value }'
        tiles = ('paginatedItems(first:150) { pageInfo { hasNextPage endCursor } edges { node { '
                 '__typename ... on EpisodeTile { ' + fields + ' } } } }')
        query = ('{ page(id:' + json.dumps(page_id) + ') { ... on ElectronicProgramGuidePage { '
                 'id brand previous { ' + tiles + ' } next { ' + tiles + ' } '
                 'current { ... on ElectronicProgramGuidePageLiveTile { tile { ' + fields + ' } } } } } }')
        data = self._fetch_public_schedule_json(provider["url"], query)
        page = (data.get("data") or {}).get("page") or {}
        if page.get("id") != page_id or page.get("brand") != provider["marker"]:
            return []
        nodes = []
        for name in ["previous", "current", "next"]:
            section = page.get(name) or {}
            if name == "current":
                if section.get("tile"):
                    nodes.append(section["tile"])
                continue
            listing = section.get("paginatedItems") or {}
            cursors = set()
            while True:
                nodes.extend(edge["node"] for edge in listing.get("edges") or [] if edge.get("node"))
                info = listing.get("pageInfo") or {}
                if not info.get("hasNextPage"):
                    break
                cursor = info.get("endCursor")
                if not cursor or cursor in cursors or len(cursors) >= 20:
                    raise ValueError("Senderprogramm konnte nicht vollständig geladen werden.")
                cursors.add(cursor)
                more_tiles = tiles.replace("first:150", "first:150,after:" + json.dumps(cursor))
                more_query = ('{ page(id:' + json.dumps(page_id) + ') { ... on ElectronicProgramGuidePage { '
                              'id brand ' + name + ' { ' + more_tiles + ' } } } }')
                more = (self._fetch_public_schedule_json(provider["url"], more_query).get("data") or {}).get("page") or {}
                if more.get("id") != page_id or more.get("brand") != provider["marker"]:
                    raise ValueError("Senderprogramm gehört nicht zum angefragten Sender und Datum.")
                listing = (more.get(name) or {}).get("paginatedItems") or {}
        raw = []
        previous_minutes = None
        offset = 0
        for item in nodes:
            clock = next((m for meta in item.get("indexMeta") or []
                          if (m := re.fullmatch(r"(\d{2}):(\d{2})u?", meta.get("value") or ""))), None)
            if not clock or not item.get("title"):
                continue
            hour, minute = map(int, clock.groups())
            if hour > 23 or minute > 59:
                continue
            minutes = hour * 60 + minute
            if previous_minutes is not None and minutes + 360 < previous_minutes:
                offset += 1
            previous_minutes = minutes
            start = self.runtime.datetime.combine(day + timedelta(days=offset), self.runtime.datetime.min.time(), self.runtime.EPG_TIMEZONE).replace(hour=hour, minute=minute)
            duration = 0
            for meta in item.get("statusMeta") or []:
                value = meta.get("value") or ""
                hours = re.search(r"(\d+)\s*u(?:ur)?\b", value)
                mins = re.search(r"(\d+)\s*min\b", value)
                if hours or mins:
                    duration = (int(hours[1]) * 60 if hours else 0) + (int(mins[1]) if mins else 0)
                    break
            raw.append({"title": item["title"], "subtitle": item.get("description") or "",
                        "start_dt": start, "duration_minutes": duration,
                        "_source_url": "https://www.vrt.be" + page_id})
        result = []
        for index, item in enumerate(raw):
            if index + 1 < len(raw):
                end = raw[index + 1]["start_dt"]
            elif 0 < item["duration_minutes"] <= 1440:
                end = item["start_dt"] + timedelta(minutes=item["duration_minutes"])
            else:
                continue
            if item["start_dt"] < end <= item["start_dt"] + timedelta(days=1):
                result.append({**item, "end_dt": end})
        return result

    def _fetch_country_official_programs(self, provider):
        today = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).date()
        raw_items = []
        kind = provider["kind"]
        marker = provider["marker"]
        for day_index in range(3):
            day = today + timedelta(days=day_index)
            date_path = day.strftime("%Y/%m/%d") if kind == "tv2no" else day.isoformat()
            url = provider["url"].format(date=date_path, guid="")
            try:
                if kind == "orf" and day_index:
                    # Follow dated links published by the broadcaster itself.
                    home = self._fetch_html(provider["url"], "ORF")
                    links = re.findall(r'href="([^"]+)"', home)
                    link = next((link for link in links if f"_day-{day:%d-%m-%Y}_" in link
                                 and link.startswith(f"/program/{marker}/")), None)
                    if not link:
                        continue
                    url = "https://tv.orf.at" + html.unescape(link)
                day_items = []
                if kind == "nrk":
                    for station in json.loads(self._fetch_html(url, "NRK")):
                        if station.get("channelId") != marker or not station.get("hasPublicEpg"):
                            continue
                        for group in station.get("transmissionGroups") or []:
                            for item in group.get("entries") or []:
                                if not item.get("title"):
                                    continue
                                try:
                                    start = self.runtime.datetime.fromisoformat(item["start"]["planned"])
                                    end = self.runtime.datetime.fromisoformat(item["end"]["planned"])
                                    if start.utcoffset() is None or end.utcoffset() is None:
                                        continue
                                    if start < self.runtime.datetime.now(self.runtime.EPG_TIMEZONE) and item["start"].get("actual") and item["end"].get("actual"):
                                        start = self.runtime.datetime.fromisoformat(item["start"]["actual"])
                                        end = self.runtime.datetime.fromisoformat(item["end"]["actual"])
                                    day_items.append({"title": item.get("title"), "desc": item.get("description") or "",
                                                      "start_dt": start, "end_dt": end, "_source_url": url})
                                except (KeyError, TypeError, ValueError):
                                    continue
                elif kind == "tv2no":
                    for station in json.loads(self._fetch_html(url, "TV 2")):
                        if station.get("channelId") != marker or station.get("date") != day.isoformat():
                            continue
                        if (station.get("channel") or {}).get("disabled"):
                            continue
                        for item in station.get("programs") or []:
                            try:
                                start = self.runtime.datetime.fromisoformat(item["startTime"])
                                end = self.runtime.datetime.fromisoformat(item["endTime"])
                                # The public Norwegian guide publishes local wall-clock times.
                                zone = ZoneInfo(self.runtime.COUNTRIES[self.country]["timezone"])
                                if start.utcoffset() is None:
                                    start = start.replace(tzinfo=zone)
                                if end.utcoffset() is None:
                                    end = end.replace(tzinfo=zone)
                                day_items.append({"title": item.get("title"), "desc": item.get("synopsis") or "",
                                                  "category": item.get("genre") or "", "start_dt": start,
                                                  "end_dt": end, "_source_url": url})
                            except (KeyError, TypeError, ValueError):
                                continue
                elif kind == "svt":
                    page = self._fetch_html(url, "SVT")
                    lines = self._html_lines(page)
                    section_title = self.runtime.normalize(f"Tablå för {marker}")
                    start_index = next(
                        (
                            index + 1
                            for index, line in enumerate(lines)
                            if self.runtime.normalize(line) == section_title
                        ),
                        None,
                    )
                    if start_index is None:
                        continue
                    zone = ZoneInfo(self.runtime.COUNTRIES[self.country]["timezone"])
                    previous_minutes = None
                    day_offset = 0
                    for line in lines[start_index:]:
                        if self.runtime.normalize(line).startswith(self.runtime.normalize("Tablå för ")):
                            break
                        match = re.match(r"^Klockan\s+(\d{1,2}):(\d{2})\s*-\s*(.+)$", line, re.I)
                        if not match:
                            continue
                        hour, minute = int(match.group(1)), int(match.group(2))
                        if hour > 23 or minute > 59:
                            continue
                        title = match.group(3).strip()
                        repeated_time = f"{hour:02d}:{minute:02d}"
                        if title.endswith(repeated_time):
                            title = title[:-5].rstrip()
                        if not title:
                            continue
                        minutes = hour * 60 + minute
                        if previous_minutes is not None and minutes + 360 < previous_minutes:
                            day_offset += 1
                        previous_minutes = minutes
                        start = self.runtime.datetime.combine(
                            day + timedelta(days=day_offset),
                            self.runtime.datetime.min.time(),
                        ).replace(tzinfo=zone).replace(
                            hour=hour,
                            minute=minute,
                            second=0,
                            microsecond=0,
                        )
                        day_items.append({
                            "title": title,
                            "subtitle": "",
                            "desc": "",
                            "category": "",
                            "start_dt": start,
                            "_source_url": url,
                        })
                    day_items = [
                        item for item in self._build_programmes_from_starts(day_items)
                        if item.get("title")
                    ]
                    converted = []
                    for item in day_items:
                        converted.append({
                            "title": item["title"],
                            "subtitle": item.get("subtitle") or "",
                            "desc": item.get("desc") or "",
                            "category": item.get("category") or "",
                            "start_dt": self.runtime.datetime.fromisoformat(item["start"]),
                            "end_dt": self.runtime.datetime.fromisoformat(item["end"]),
                            "_source_url": url,
                        })
                    day_items = converted
                elif kind == "npo":
                    stations = json.loads(self._fetch_html(provider["channels_url"], "NPO"))
                    station = next((s for s in stations if s.get("title") == marker), None)
                    if not station:
                        continue
                    url = provider["url"].format(date=day.strftime("%d-%m-%Y"), guid=station["guid"])
                    for item in json.loads(self._fetch_html(url, "NPO")):
                        start = self.runtime.datetime.fromtimestamp(int(item["programStart"]), self.runtime.EPG_TIMEZONE)
                        end = self.runtime.datetime.fromtimestamp(int(item["programEnd"]), self.runtime.EPG_TIMEZONE)
                        day_items.append({
                            "title": item.get("mainTitle"), "subtitle": item.get("episodeTitle") or "",
                            "desc": item.get("synopsis") or "", "start_dt": start, "end_dt": end,
                            "_source_url": url,
                        })
                elif kind == "vrt":
                    day_items = self._fetch_vrt_programmes(provider, day)
                elif kind == "vtm":
                    page = self._fetch_html(url, "VTM")
                    for body in re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.I | re.S):
                        data = json.loads(body)
                        for item in data if isinstance(data, list) else [data]:
                            if item.get("@type") != "BroadcastEvent" or item.get("publishedOn", {}).get("name") != marker:
                                continue
                            day_items.append({
                                "title": item.get("name"), "desc": item.get("description") or "",
                                "start_dt": self.runtime.datetime.fromisoformat(item["startDate"]),
                                "end_dt": self.runtime.datetime.fromisoformat(item["endDate"]), "_source_url": url,
                            })
                elif kind == "srg":
                    page = self._fetch_html(url, kind.upper())
                    guide = json.loads(page)
                    for station in guide.get("programGuide", []):
                        if self.runtime.normalize(station.get("channel", {}).get("title")) != self.runtime.normalize(marker):
                            continue
                        for item in station.get("programList", []):
                            day_items.append({
                                "title": item.get("title"), "subtitle": item.get("subtitle") or "",
                                "desc": item.get("description") or item.get("broadcastInfo") or "",
                                "start_dt": self.runtime.datetime.fromisoformat(item["startTime"]),
                                "end_dt": self.runtime.datetime.fromisoformat(item["endTime"]),
                                "_source_url": url,
                            })
                elif kind == "orf":
                    page = self._fetch_html(url, kind.upper())
                    for attrs, content in re.findall(r'<li\b([^>]*\bdata-start-time=[^>]*)>(.*?)</li>', page, re.I | re.S):
                        attributes = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
                        if attributes.get("data-channel") != marker:
                            continue
                        title = re.search(r'<div\b[^>]*class="series-title"[^>]*>(.*?)</div>', content, re.I | re.S)
                        subtitle = re.search(r'<div\b[^>]*class="episode-title"[^>]*>(.*?)</div>', content, re.I | re.S)
                        if not title:
                            continue
                        day_items.append({
                            "title": html.unescape(re.sub(r"<[^>]+>", "", title[1])).strip(),
                            "subtitle": html.unescape(re.sub(r"<[^>]+>", "", subtitle[1])).strip() if subtitle else "",
                            "start_dt": self.runtime.datetime.fromisoformat(attributes["data-start-time"]),
                            "end_dt": self.runtime.datetime.fromisoformat(attributes["data-end-time"]),
                            "_source_url": url,
                        })
                elif kind == "play":
                    page = self._fetch_html(url, kind.upper())
                    chunks = []
                    for block in re.findall(r'self\.__next_f\.push\((\[.*?\])\)</script>', page, re.S):
                        value = json.loads(block)
                        if value[0] == 1 and isinstance(value[1], str):
                            chunks.append(value[1])
                    text = "".join(chunks)
                    # The response must identify the requested date and channel.
                    if f'"activeBrand":"{marker}"' not in text or f'"activeDate":"{day.isoformat()}"' not in text:
                        continue
                    decoder = json.JSONDecoder()
                    for match in re.finditer(r'"program":(?=\{)', text):
                        try:
                            item, _ = decoder.raw_decode(text, match.end())
                            if item.get("dateString") != day.isoformat():
                                continue
                            start = self.runtime.datetime.fromtimestamp(int(item["timestamp"]), self.runtime.EPG_TIMEZONE)
                            duration = int(item["duration"])
                            if not 0 < duration <= 86400:
                                continue
                            day_items.append({
                                "title": item["programTitle"], "subtitle": item.get("episodeTitle") or "",
                                "desc": item.get("contentEpisode") or "", "category": item.get("genre") or "",
                                "start_dt": start, "end_dt": start + timedelta(seconds=duration),
                                "_source_url": url,
                            })
                        except (KeyError, TypeError, ValueError):
                            continue
                raw_items.extend([
                    item for item in day_items
                    if item["start_dt"].utcoffset() is not None
                    and day <= item["start_dt"].astimezone(self.runtime.EPG_TIMEZONE).date() <= day + timedelta(days=kind in {"vrt", "svt"})
                ])
            except (KeyError, TypeError, ValueError, OSError) as exc:
                print(f"[TV Guide] Senderquelle {kind} für {day}: {exc}", flush=True)
                continue
        valid = [item for item in raw_items if item.get("title")
                 and item["start_dt"].utcoffset() is not None and item["end_dt"].utcoffset() is not None
                 and today <= item["start_dt"].astimezone(self.runtime.EPG_TIMEZONE).date() < today + timedelta(days=3)
                 and item["end_dt"] > item["start_dt"]]
        for item in valid:
            item["start_dt"] = item["start_dt"].astimezone(self.runtime.EPG_TIMEZONE)
            item["end_dt"] = item["end_dt"].astimezone(self.runtime.EPG_TIMEZONE)
        programmes = self._build_programmes_from_starts(valid)
        by_start = {item["start_dt"].isoformat(): item for item in valid}
        for item in programmes:
            original = by_start[item["start"]]
            item["_source_url"] = original["_source_url"]
            if original["end_dt"] - original["start_dt"] <= timedelta(days=1):
                item["end"] = original["end_dt"].isoformat()
        return programmes

    def _fetch_official_programs(self, channel_id, provider):
        kind = provider.get("kind")
        handler_spec = self.OFFICIAL_PROVIDER_HANDLERS.get(kind)
        if handler_spec:
            method_name, argument_mode = handler_spec
            handler = getattr(self, method_name)
            if argument_mode == "provider":
                return handler(provider)
            return handler()
        return self._fetch_generic_official_programs(channel_id, provider)

    def _fetch_swr_programs(self):
        today = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).date()
        raw_items = []

        for day_index in range(3):
            schedule_date = today + timedelta(days=day_index)
            try:
                page = self._fetch_html(
                    self.runtime.SWR_PROGRAM_URL.format(date=schedule_date.isoformat()), "SWR",
                )
            except Exception as exc:
                print(f"[TV Guide] SWR-Seite nicht verfügbar, nutze ARD-Senderdaten: {exc}", flush=True)
                continue
            lines = self._html_lines(page)

            pending_start = None
            for line in lines:
                match = re.match(
                    r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})$",
                    line,
                )
                if match:
                    day, month, year, hour, minute = map(int, match.groups())
                    try:
                        date_value = self.runtime.datetime(year, month, day).date()
                    except ValueError:
                        pending_start = None
                        continue
                    pending_start = self.runtime.datetime.combine(
                        date_value,
                        self.runtime.datetime.min.time(),
                    ).replace(tzinfo=self.runtime.EPG_TIMEZONE).replace(
                        hour=hour,
                        minute=minute,
                        second=0,
                        microsecond=0,
                    )
                    continue

                if pending_start is None:
                    continue

                title = line.strip()
                if not title:
                    continue
                normalized = self.runtime.normalize(title)
                if normalized in {
                    "untertitel",
                    "wiederholung",
                    "tagestipp",
                    "deutschegebardensprache",
                    "audiodeskription",
                }:
                    continue
                if title.startswith(("Stand", "Erstmals publiziert", "Autor/in")):
                    continue
                if len(title) > 240:
                    continue

                raw_items.append({
                    "title": title,
                    "subtitle": "",
                    "desc": "",
                    "category": "",
                    "start_dt": pending_start,
                    "icon": None,
                })
                pending_start = None

        if raw_items:
            return self._build_programmes_from_starts(raw_items)
        return self._fetch_generic_official_programs(
            "swr", {"kind": "ard", "marker": "SWR Baden-Württemberg"},
        )

    def _fetch_sr_programs(self):
        today = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).date()
        programmes = []

        for day_index in range(3):
            schedule_date = today + timedelta(days=day_index)
            page = self._fetch_html(
                self.runtime.SR_PROGRAM_URL.format(date=schedule_date.isoformat()),
                "SR",
            )
            raw_items = []
            for attributes, content in re.findall(r"<li\b([^>]*\bdata-pg-show-start=[^>]*)>(.*?)</li>", page, re.I | re.S):
                attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', attributes))
                title_match = re.search(r'<a\b[^>]*\btitle="([^"]+)"', content)
                try:
                    start = self.runtime.datetime.fromisoformat(attrs["data-pg-show-start"])
                    duration = int(attrs["data-pg-show-duration"])
                    if title_match and start.utcoffset() is not None and start.date() == schedule_date and 0 < duration <= 360:
                        raw_items.append({
                            "title": html.unescape(title_match[1]), "start_dt": start,
                            "end_dt": start + timedelta(minutes=duration),
                        })
                except (KeyError, TypeError, ValueError):
                    continue
            day_programmes = self._build_programmes_from_starts(raw_items)
            programmes.extend(day_programmes)

        return self._merge_program_lists([], programmes)

    def _supplement_missing_channels(self, channels):
        by_id = {channel["id"]: channel for channel in channels}
        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)
        self._official_html_cache = {}
        self._official_fetch_errors = {}
        enriched = 0
        attempted = 0
        provider_results = {}

        try:
            for channel_id in self.runtime.base_channel_ids(self):
                channel = by_id.get(channel_id)
                provider = self.provider_audit.get(channel_id)
                if not channel:
                    provider_results[channel_id] = {
                        "status": "channel_missing",
                        "programmes": 0,
                    }
                    continue
                secondary_provider = self.runtime.COUNTRIES[self.country].get("secondary_providers", {}).get(channel_id)
                secondary_url = secondary_provider.get("url") if secondary_provider else self.runtime.SECONDARY_WEB_PROVIDER_BY_CHANNEL.get(channel_id)
                if not provider and not secondary_url:
                    provider_results[channel_id] = {
                        "status": "no_verified_provider",
                        "programmes": 0,
                    }
                    continue

                attempted += 1
                try:
                    def fetch_independently(fetcher):
                        try:
                            return fetcher()
                        except Exception as exc:
                            print(f"[TV Guide] Einzelne Webquelle für {channel_id} übersprungen: {exc}", flush=True)
                            return []

                    official = fetch_independently(lambda: self._fetch_official_programs(channel_id, provider)) if provider else []
                    teletext = fetch_independently(lambda: self._fetch_teletext_programs(channel_id))
                    secondary = fetch_independently(lambda: self._fetch_official_programs(channel_id, secondary_provider)
                                                    if secondary_provider else self._fetch_secondary_web_programs(channel_id))

                    for item in official:
                        item["_source"] = "official"
                        item["_source_kind"] = "broadcaster"
                        source_template = provider.get("url") or {
                            "ard": self.runtime.ARD_PROGRAM_URL, "zdf": self.runtime.ZDF_PROGRAM_URL,
                            "swr": self.runtime.SWR_PROGRAM_URL, "sr": self.runtime.SR_PROGRAM_URL,
                            "radiobremen": self.runtime.ARD_RB_PROGRAM_URL,
                        }.get(provider.get("kind"), "")
                        if not item.get("_source_url"):
                            item["_source_url"] = source_template.format(date=self.runtime.datetime.fromisoformat(item["start"]).astimezone(self.runtime.EPG_TIMEZONE).date().isoformat(), guid="")
                        item["_source_rank"] = 450
                    for item in teletext:
                        item["_source"] = "teletext"
                        item["_source_kind"] = "broadcaster-teletext"
                        item["_source_rank"] = 500
                    for item in secondary:
                        item["_source"] = "secondary-web"
                        item["_source_kind"] = "secondary-web"
                        item["_source_rank"] = 300

                    official = self._merge_program_lists(official, teletext)
                    official = self._merge_program_lists(official, secondary)
                    official = [
                        item for item in official
                        if self.runtime.datetime.fromisoformat(item["end"]) >= now - timedelta(hours=6)
                    ]
                    if not official:
                        provider_results[channel_id] = {
                            "status": "no_data",
                            "programmes": 0,
                            "teletext": bool(teletext),
                            "secondary": bool(secondary),
                        }
                        continue

                    before_count = len(channel.get("programs") or [])
                    merged = self._merge_program_lists(channel.get("programs") or [], official)
                    if not merged:
                        provider_results[channel_id] = {
                            "status": "no_data",
                            "programmes": 0,
                            "teletext": bool(teletext),
                        }
                        continue

                    channel["programs"] = merged
                    channel["available"] = True
                    source_label = (
                        provider.get("url") or provider.get("kind")
                        if provider else "Sekundäre Web-Programmquelle"
                    )
                    if self.runtime.TELETEXT_PROVIDER_BY_CHANNEL.get(channel_id):
                        source_label = f"{source_label} + Videotext"
                    if secondary_url:
                        source_label = f"{source_label} + Sekundärquelle"
                    channel["official_source"] = source_label
                    if before_count == 0:
                        channel["source_name"] = (
                            f"Offizielle Quelle – {channel.get('name')}"
                            if provider
                            else f"Sekundäre Webquelle – {channel.get('name')}"
                        )
                    else:
                        addition = "offizielle Quelle" if provider else "Sekundärquelle"
                        channel["source_name"] = (
                            f"{channel.get('source_name') or 'XMLTV'} + {addition}"
                        )
                    enriched += 1
                    provider_results[channel_id] = {
                        "status": "ok",
                        "programmes": len(official),
                        "merged_programmes": len(merged),
                        "teletext": bool(teletext),
                        "secondary": bool(secondary),
                    }
                except Exception as exc:
                    provider_results[channel_id] = {
                        "status": "error",
                        "programmes": 0,
                        "error": str(exc)[:240],
                    }
                    print(
                        f"[TV Guide] Offizielle Provider-Ergänzung fehlgeschlagen für "
                        f"{channel.get('name')}: {exc}",
                        flush=True,
                    )
        finally:
            self._official_html_cache = {}
            self._official_fetch_errors = {}

        missing_official = [
            channel_id
            for channel_id in self.runtime.base_channel_ids(self)
            if self.provider_audit.get(channel_id) is None
        ]
        self.official_metrics = {
            "attempted": attempted,
            "enriched": enriched,
            "teletext_channels": len(self.runtime.TELETEXT_PROVIDER_BY_CHANNEL) if self.country == "de" else 0,
            "secondary_web_channels": len(self.runtime.SECONDARY_WEB_PROVIDER_BY_CHANNEL) if self.country == "de" else len(self.runtime.COUNTRIES[self.country].get("secondary_providers", {})),
            "missing_official": missing_official,
            "provider_results": provider_results,
        }
        print(
            f"[TV Guide] Provider-Abdeckung: {enriched}/{attempted} Sender ergänzt; "
            f"{len(missing_official)} ohne offiziellen Endpunkt, "
            f"{self.official_metrics['secondary_web_channels']} davon mit Sekundärquelle",
            flush=True,
        )
        for channel_id in self.runtime.base_channel_ids(self):
            result = provider_results.get(channel_id, {"status": "unknown"})
            print(
                f"[TV Guide] Provider-Check {channel_id}: "
                f"{result.get('status')} ({result.get('programmes', 0)} Programme)",
                flush=True,
            )
        for channel in channels:
            channel["programs"] = self._validate_program_timeline(
                channel.get("programs") or []
            )
            channel["available"] = bool(channel["programs"])

        return channels

