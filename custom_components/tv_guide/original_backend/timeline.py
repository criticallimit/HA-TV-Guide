"""Programme priorities, deduplication, merging and coverage.


The application context is supplied by services.py; all mutable state is shared.
"""

import re
from datetime import timedelta


class ProgrammeTimeline:
    def _retain_cached_programmes(self, channels):
        """Keep still-valid cache entries only in slots not covered by fresh data."""
        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)
        cached = {channel["id"]: channel for channel in self.channels}
        fresh_ids = {channel["id"] for channel in channels}
        excluded = set(self.runtime.COUNTRIES[self.country].get("excluded_xmltv_ids", []))
        for old in self.channels:
            if old["id"] not in fresh_ids and not (excluded.intersection(old.get("xmltv_ids") or [])
                                                   or old.get("source_id") in excluded):
                channels.append({**old, "programs": [], "available": False})
        for channel in channels:
            fresh = channel.get("programs") or []
            intervals = []
            for item in fresh:
                intervals.append((self.runtime.datetime.fromisoformat(item["start"]),
                                  self.runtime.datetime.fromisoformat(item["end"])))
            retained = []
            for item in cached.get(channel["id"], {}).get("programs") or []:
                try:
                    start = self.runtime.datetime.fromisoformat(item["start"])
                    end = self.runtime.datetime.fromisoformat(item["end"])
                    if (start.utcoffset() is None or end.utcoffset() is None or end <= now
                            or not start < end <= start + timedelta(days=1)):
                        continue
                    # Old official priorities must never override a newly
                    # published correction, even from a lower-ranked feed.
                    if any(start < fresh_end and end > fresh_start for fresh_start, fresh_end in intervals):
                        continue
                    retained.append(dict(item))
                except (KeyError, TypeError, ValueError):
                    continue
            channel["programs"] = self._validate_program_timeline(fresh + retained)
            channel["available"] = bool(channel["programs"])
        return channels

    def _validate_feed_quality(self, channels):
        available = sum(1 for channel in channels if channel.get("available"))
        main_available = sum(
            1 for channel in channels
            if channel.get("preset") and channel.get("available")
        )
        programme_count = sum(
            len(channel.get("programs") or [])
            for channel in channels
            if channel.get("available")
        )
        latest_end = (
            self.runtime.datetime.fromisoformat(self.feed_latest_end)
            if self.feed_latest_end else None
        )
        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)

        # Partial sources are useful in a merge architecture. Reject only
        # feeds that contain no usable programmes or are already effectively
        # stale. A small source may still fill a gap that larger feeds miss.
        if available < 1 or programme_count < 1:
            raise ValueError("EPG-Quelle enthält keine verwertbaren Programmdaten.")
        if latest_end is None or latest_end < now + timedelta(hours=2):
            raise ValueError(
                "EPG-Quelle enthält keine ausreichend aktuellen Programmdaten."
            )

        coverage = "breit" if available >= 80 and main_available >= min(25, len(self.catalog["channels"])) else "teilweise"
        print(
            f"[TV Guide] EPG-Qualität akzeptiert ({coverage}): "
            f"{available} Sender mit Programmdaten, {main_available}/{len(self.catalog['channels'])} Hauptsender, "
            f"{programme_count} Programme, Daten bis {latest_end.isoformat()}",
            flush=True,
        )

    def _tag_programmes(self, channels, source_name, source_rank):
        for channel in channels:
            for item in channel.get("programs") or []:
                item["_source"] = source_name
                item["_source_kind"] = "community"
                item["_source_rank"] = int(source_rank)
        return channels

    def _programme_priority(self, item):
        return (
            self._source_trust(item),
            int(item.get("_source_rank") or 0),
            self._programme_score(item),
            len(str(item.get("desc") or "")),
        )

    def _source_trust(self, item):
        if item.get("_source_kind") == "broadcaster" or item.get("_source") == "official":
            return 2
        if item.get("_source_kind") == "broadcaster-teletext" or item.get("_source") == "teletext":
            return 1
        return 0

    def _programme_score(self, item):
        return sum(
            1 for key in ("title", "subtitle", "desc", "category", "icon")
            if str(item.get(key) or "").strip()
        ) + min(len(str(item.get("desc") or "")) // 80, 4)

    def _title_key(self, value):
        return self.runtime.normalize(re.sub(r"\b(?:folge|episode)\s*\d+\b", "", str(value or ""), flags=re.I))

    def _same_programme(self, left, right, tolerance_minutes=4):
        left_start = left.get("start")
        right_start = right.get("start")
        if not left_start or not right_start:
            return False
        try:
            delta = abs(
                (
                    self.runtime.datetime.fromisoformat(left_start)
                    - self.runtime.datetime.fromisoformat(right_start)
                ).total_seconds()
            )
        except Exception:
            return False
        if delta > tolerance_minutes * 60:
            return False

        left_title = self._title_key(left.get("title"))
        right_title = self._title_key(right.get("title"))
        if not left_title or not right_title:
            return delta <= 60
        if left_title == right_title:
            return True
        shorter, longer = sorted((left_title, right_title), key=len)
        return len(shorter) >= 5 and shorter in longer

    def _merge_programme_metadata(self, preferred, alternate):
        merged = dict(preferred)
        if self._source_trust(preferred) > self._source_trust(alternate):
            return merged
        for key in ("title", "subtitle", "desc", "category", "icon", "end"):
            current = str(merged.get(key) or "").strip()
            candidate = str(alternate.get(key) or "").strip()
            if not current and candidate:
                merged[key] = alternate.get(key)
            elif key == "desc" and len(candidate) > len(current):
                merged[key] = alternate.get(key)
        return merged

    def _slot_conflict(self, left, right, tolerance_minutes=2):
        try:
            left_start = self.runtime.datetime.fromisoformat(left.get("start") or "")
            right_start = self.runtime.datetime.fromisoformat(right.get("start") or "")
        except Exception:
            return False
        return abs((left_start - right_start).total_seconds()) <= tolerance_minutes * 60

    def _same_overlapping_programme(self, left, right, min_overlap_ratio=0.5):
        left_title = self._title_key(left.get("title"))
        right_title = self._title_key(right.get("title"))
        if not left_title or not right_title:
            return False
        if left_title != right_title:
            shorter, longer = sorted((left_title, right_title), key=len)
            if len(shorter) < 5 or shorter not in longer:
                return False

        try:
            left_start = self.runtime.datetime.fromisoformat(left.get("start") or "")
            left_end = self.runtime.datetime.fromisoformat(left.get("end") or "")
            right_start = self.runtime.datetime.fromisoformat(right.get("start") or "")
            right_end = self.runtime.datetime.fromisoformat(right.get("end") or "")
        except Exception:
            return False

        overlap = (min(left_end, right_end) - max(left_start, right_start)).total_seconds()
        if overlap <= 0:
            return False
        shortest = min(
            (left_end - left_start).total_seconds(),
            (right_end - right_start).total_seconds(),
        )
        return shortest > 0 and overlap / shortest >= min_overlap_ratio

    def _prefer_programme(self, left, right):
        left_priority = self._programme_priority(left)
        right_priority = self._programme_priority(right)
        if not (self._same_programme(left, right) or self._same_overlapping_programme(left, right)):
            return dict(right if right_priority > left_priority else left)
        if right_priority > left_priority:
            return self._merge_programme_metadata(right, left)
        return self._merge_programme_metadata(left, right)

    def _merge_program_lists(self, existing, incoming):
        merged = [dict(item) for item in (existing or []) if item.get("start")]

        for item in incoming or []:
            if not item.get("start"):
                continue

            same_index = next(
                (
                    index
                    for index, current in enumerate(merged)
                    if self._same_programme(current, item)
                ),
                None,
            )
            if same_index is not None:
                merged[same_index] = self._prefer_programme(
                    merged[same_index],
                    item,
                )
                continue

            slot_index = next(
                (
                    index
                    for index, current in enumerate(merged)
                    if self._slot_conflict(current, item)
                ),
                None,
            )
            if slot_index is not None:
                merged[slot_index] = self._prefer_programme(
                    merged[slot_index],
                    item,
                )
                continue

            merged.append(dict(item))

        return self._validate_program_timeline(merged)

    def _validate_program_timeline(self, programmes):
        ordered = []
        for item in programmes:
            try:
                start = self.runtime.datetime.fromisoformat(item.get("start") or "")
                end = self.runtime.datetime.fromisoformat(item.get("end") or "")
                if start.utcoffset() is None or end.utcoffset() is None or end <= start:
                    continue
            except (AttributeError, TypeError, ValueError):
                continue
            ordered.append((start, end, dict(item)))
        # ISO strings do not sort chronologically across different UTC offsets,
        # especially within the repeated hour at the end of daylight saving.
        ordered.sort(key=lambda entry: entry[0])
        result = []

        for item_start, item_end, item in ordered:
            discard_item = False
            while result:
                previous = result[-1]
                try:
                    previous_start = self.runtime.datetime.fromisoformat(previous.get("start") or "")
                    previous_end = self.runtime.datetime.fromisoformat(previous.get("end") or "")
                except Exception:
                    result.pop()
                    continue

                if item_start >= previous_end:
                    break

                # Same programme from different sources can be shifted by
                # several minutes. Collapse it when the titles match and most
                # of the shorter interval overlaps, even for old cache entries
                # that no longer carry source metadata.
                if self._same_overlapping_programme(previous, item):
                    result[-1] = self._prefer_programme(previous, item)
                    discard_item = True
                    break

                # Same/near start: two sources describe the same linear-TV slot.
                if abs((item_start - previous_start).total_seconds()) <= 2 * 60:
                    result[-1] = self._prefer_programme(previous, item)
                    discard_item = True
                    break

                previous_rank = self._programme_priority(previous)[:2]
                item_rank = self._programme_priority(item)[:2]

                if previous_rank == item_rank:
                    # One source produced an overlapping schedule. Preserve the
                    # ordering and end the previous programme at the next start.
                    previous["end"] = item_start.isoformat()
                    if self.runtime.datetime.fromisoformat(previous["end"]) <= previous_start:
                        result.pop()
                        continue
                    break

                if item_rank > previous_rank:
                    # The higher-priority source supersedes the overlapping
                    # lower-priority entry.
                    result.pop()
                    continue

                # Existing higher-priority programme owns this time slot.
                discard_item = True
                break

            if not discard_item:
                result.append(item)

        return result

    def coverage_metrics(self, now=None):
        """Report actual main-channel coverage, independently of feed availability."""
        now = (now or self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)).astimezone(self.runtime.EPG_TIMEZONE)
        mains = [ch for ch in self.channels if ch.get("preset")]
        intervals = {}
        for channel in mains:
            slots = []
            for item in channel.get("programs") or []:
                try:
                    start, end = (self.runtime.datetime.fromisoformat(item[key]) for key in ["start", "end"])
                    if start.utcoffset() is not None and end.utcoffset() is not None and end > start:
                        slots.append((start, end))
                except (KeyError, TypeError, ValueError):
                    continue
            intervals[channel["id"]] = slots
        missing = [ch["id"] for ch in mains
                   if not any(start <= now < end for start, end in intervals[ch["id"]])]
        days = []
        for offset in range(3):
            start = self.runtime.datetime.combine(now.date() + timedelta(days=offset), self.runtime.datetime.min.time(), self.runtime.EPG_TIMEZONE)
            end = start + timedelta(days=1)
            absent = [ch["id"] for ch in mains
                      if not any(left < end and right > start for left, right in intervals[ch["id"]])]
            evening_start = start + timedelta(hours=18)
            evening_end = start + timedelta(hours=23)
            evening_absent = [ch["id"] for ch in mains
                              if not any(left < evening_end and right > evening_start
                                         for left, right in intervals[ch["id"]])]
            days.append({"date": start.date().isoformat(), "channels_with_programmes": len(mains) - len(absent),
                         "missing_channels": absent, "channels_with_evening_programmes": len(mains) - len(evening_absent),
                         "missing_evening_channels": evening_absent})
        return {"main_channels": len(mains), "current_channels": len(mains) - len(missing),
                "missing_current_channels": missing, "days": days}

    def _source_quality_metrics(self, channels, url, latest_end):
        available = [channel for channel in channels if channel.get("available")]
        main_available = [
            channel for channel in available if channel.get("preset")
        ]
        programme_count = sum(len(channel.get("programs") or []) for channel in available)
        return {
            "url": url,
            "ok": True,
            "coverage": (
                "broad"
                if len(available) >= 80 and len(main_available) >= min(25, len(self.catalog["channels"]))
                else "partial"
            ),
            "channels": len(channels),
            "available_channels": len(available),
            "main_channels": len(main_available),
            "programmes": programme_count,
            "latest_end": latest_end.isoformat() if latest_end else None,
        }

    def _quarantine_conflicting_fallback(self, channel_sets):
        references = {}
        for channels in channel_sets:
            for channel in channels:
                items = channel.get("programs") or []
                if items and items[0].get("_source") in {self.runtime.OPEN_EPG_URL, self.runtime.EPGSHARE_EPG_URL}:
                    references.setdefault(channel["id"], []).append(items)
        quarantined = []
        compared_channels = 0
        for channels in channel_sets:
            for channel in channels:
                items = channel.get("programs") or []
                sources = references.get(channel["id"], [])
                if not items or items[0].get("_source") != self.runtime.EPGPW_EPG_URL or len(sources) != 2:
                    continue
                compared = mismatched = 0
                for item in items:
                    start = self.runtime.datetime.fromisoformat(item["start"])
                    end = self.runtime.datetime.fromisoformat(item["end"])
                    midpoint = start + (end - start) / 2
                    matches = [next((entry for entry in source if
                        self.runtime.datetime.fromisoformat(entry["start"]) <= midpoint < self.runtime.datetime.fromisoformat(entry["end"])
                    ), None) for source in sources]
                    if not all(matches) or not self._same_overlapping_programme(*matches):
                        continue
                    compared += 1
                    title = self._title_key(item.get("title"))
                    reference = self._title_key(matches[0].get("title"))
                    if title != reference and not (min(len(title), len(reference)) >= 5 and (title in reference or reference in title)):
                        mismatched += 1
                if compared >= 3:
                    compared_channels += 1
                if compared >= 3 and mismatched / compared >= 0.8:
                    channel["programs"] = []
                    channel["available"] = False
                    quarantined.append(channel["id"])
                    print(f"[TV Guide] Widersprüchliche epg.pw-Daten verworfen für {channel['id']}: {mismatched}/{compared} bestätigte Zeitslots abweichend", flush=True)
        if len(quarantined) >= 5 and len(quarantined) / compared_channels >= 0.8:
            for channels in channel_sets:
                for channel in channels:
                    items = channel.get("programs") or []
                    if items and items[0].get("_source") == self.runtime.EPGPW_EPG_URL:
                        channel["programs"] = []
                        channel["available"] = False
                        quarantined.append(channel["id"])
            print("[TV Guide] epg.pw wegen systematisch widersprüchlicher Sendungsdaten vollständig quarantänisiert.", flush=True)
        return quarantined

    def _merge_channel_sets(self, channel_sets):
        merged = {}
        dynamic_names = {}

        for channels in channel_sets:
            for incoming in channels:
                channel_id = incoming.get("id")
                if not channel_id:
                    continue

                target_id = channel_id
                if not incoming.get("preset"):
                    name_key = self.runtime.normalize(incoming.get("source_name") or incoming.get("name"))
                    if name_key and name_key in dynamic_names:
                        target_id = dynamic_names[name_key]
                    elif name_key:
                        dynamic_names[name_key] = channel_id

                if target_id not in merged:
                    merged[target_id] = dict(incoming)
                    merged[target_id]["programs"] = self._validate_program_timeline(
                        incoming.get("programs") or []
                    )
                    continue

                target = merged[target_id]
                for key in ("logo", "logo_light", "logo_dark", "source_name", "source_id"):
                    if not target.get(key) and incoming.get(key):
                        target[key] = incoming[key]

                target["programs"] = self._merge_program_lists(
                    target.get("programs") or [],
                    incoming.get("programs") or [],
                )
                target["available"] = bool(target["programs"])

        result = list(merged.values())
        result.sort(key=lambda ch: (
            0 if ch.get("preset") else 1,
            ch.get("order", 99999) if ch.get("preset") else 99999,
            str(ch.get("name") or "").casefold(),
        ))
        return result

