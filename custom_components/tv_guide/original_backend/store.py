"""Persistent programme cache, country state and refresh lifecycle.


The application context is supplied by services.py; all mutable state is shared.
"""

import gzip
import json
import os
import threading
import time
from datetime import timedelta, timezone
from urllib.parse import urlparse
from urllib.request import Request

from .cache_catalogue import write_catalogue
from .french_sources import FrenchProgrammeSources
from .public_schedules import PublicProgrammeSources
from .regional_sources import RegionalProgrammeSources
from .sources import ProgrammeSources
from .timeline import ProgrammeTimeline


class GuideStore(FrenchProgrammeSources, RegionalProgrammeSources, PublicProgrammeSources, ProgrammeSources, ProgrammeTimeline):
    @property
    def country(self):
        return getattr(self, "_country", "de")

    @property
    def catalog(self):
        return self.runtime.CHANNELS if self.country == "de" else self.runtime.COUNTRY_CATALOGS[self.country]

    @property
    def source_urls(self):
        return self.runtime.BUILTIN_EPG_URLS if self.country == "de" else self.runtime.COUNTRIES[self.country]["sources"]

    @property
    def provider_audit(self):
        if self.country == "de":
            return self.runtime.OFFICIAL_PROVIDER_AUDIT
        providers = self.runtime.COUNTRIES[self.country].get("providers", {})
        return {ch["id"]: providers.get(ch["id"]) for ch in self.catalog["channels"]}

    @property
    def cache_file(self):
        return self.runtime.country_file(self.runtime.CACHE_FILE, self.country)

    @property
    def parsed_cache_file(self):
        return self.runtime.country_file(self.runtime.PARSED_CACHE_FILE, self.country)

    def __init__(self, country=None):
        self._country = self.runtime.country_code(country or self.runtime.load_options().get("country"))
        self.lock = threading.Lock()
        self.options = self.runtime.load_options()
        self.channels = [{
            **ch,
            "available": False,
            "programs": [],
            "source_name": None,
            "source_id": None,
            "logo": None,
        } for ch in sorted(self.catalog["channels"], key=lambda x: x["order"])]
        self.last_error = None
        self.last_loaded = None
        self.refresh_running = False
        self.feed_latest_end = None
        self.last_refresh_attempt = 0
        self.source_metrics = []
        self.cache_schema_current = True
        self.official_metrics = {
            "attempted": 0,
            "enriched": 0,
            "teletext_channels": 0,
            "missing_official": [],
        }
        self._load_parsed_cache()

    def _load_parsed_cache(self):
        try:
            payload = json.loads(self.parsed_cache_file.read_text(encoding="utf-8"))
            if payload.get("country", "de") != self.country:
                return False
            cache_version = int(payload.get("schema_version") or 0)
            self.cache_schema_current = cache_version == self.runtime.PARSED_CACHE_SCHEMA_VERSION
            if cache_version in {5, 6, 7}:
                print(f"[TV Guide] Cache-Schema {cache_version} wird mit bestätigten Senderquellen neu aufgebaut.", flush=True)
                return False
            if not self.cache_schema_current:
                print(
                    f"[TV Guide] EPG-Cache-Version {cache_version} ist veraltet; "
                    f"vorhandene Daten bleiben sichtbar und werden im Hintergrund "
                    f"mit Version {self.runtime.PARSED_CACHE_SCHEMA_VERSION} neu aufgebaut.",
                    flush=True,
                )
            latest_end_raw = payload.get("feed_latest_end")

            cached_channels = [
                item for item in payload.get("channels", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id")
            ]
            for item in cached_channels:
                retained = []
                programmes = item.get('programs')
                for programme in programmes if isinstance(programmes, list) else []:
                    if not isinstance(programme, dict) or not isinstance(programme.get('title'), str):
                        continue
                    try:
                        start = self.runtime.datetime.fromisoformat(programme['start'])
                        end = self.runtime.datetime.fromisoformat(programme['end'])
                        if start.tzinfo is not None:
                            start.astimezone(timezone.utc)
                        if end.tzinfo is not None:
                            end.astimezone(timezone.utc)
                    except (KeyError, TypeError, ValueError, OverflowError):
                        continue
                    if start.tzinfo is None or end.tzinfo is None or end <= start:
                        continue
                    retained.append(programme)
                item['programs'] = retained
                item['available'] = bool(retained)
            try:
                latest = self.runtime.datetime.fromisoformat(latest_end_raw)
                if latest.tzinfo is None:
                    latest_end_raw = None
                else:
                    latest.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                latest_end_raw = None
            if cache_version < 10:
                # Old RTL records can contain reversed series/episode fields.
                # Keep other source data while these records are fetched again.
                for item in cached_channels:
                    programmes = item.get("programs") or []
                    retained = []
                    for programme in programmes:
                        source = urlparse(str(programme.get("_source_url") or ""))
                        if source.hostname in {"rtl.de", "www.rtl.de"} and source.path.startswith("/fernsehprogramm/"):
                            continue
                        retained.append(programme)
                    if len(retained) != len(programmes):
                        item["programs"] = retained
                        item["available"] = bool(retained)
            configured_by_id = {ch["id"]: ch for ch in self.catalog["channels"]}

            excluded = set(self.runtime.COUNTRIES[self.country].get("excluded_xmltv_ids", []))
            restored = []
            for item in cached_channels:
                if item.get("source_id") in excluded or excluded.intersection(item.get("xmltv_ids") or []):
                    continue
                channel_id = item["id"]
                if channel_id in configured_by_id:
                    restored.append({
                        **item,
                        # Current curated identity, ordering and artwork win
                        # over metadata left in an older programme cache.
                        **configured_by_id[channel_id],
                        "preset": True,
                        "catalog_group": "Hauptsender",
                    })
                else:
                    restored.append({**item, 'name': str(item.get('name') or channel_id)})

            # Older caches may not contain every configured main channel yet.
            existing_ids = {item["id"] for item in restored}
            for ch in sorted(self.catalog["channels"], key=lambda x: x["order"]):
                if ch["id"] in existing_ids:
                    continue
                restored.append({
                    **ch,
                    "preset": True,
                    "catalog_group": "Hauptsender",
                    "available": False,
                    "programs": [],
                    "source_name": None,
                    "source_id": None,
                    "logo": None,
                    "logo_light": ch.get("logo_file_light") or ch.get("logo_file"),
                    "logo_dark": ch.get("logo_file") or ch.get("logo_file_light"),
                })

            if not any(item.get("programs") for item in restored):
                return False

            restored.sort(key=lambda ch: (
                0 if ch.get("preset") else 1,
                ch.get("order", 99999) if ch.get("preset") else 99999,
                str(ch.get("name") or "").casefold(),
            ))

            self.channels = restored
            self.last_loaded = payload.get("last_loaded") or payload.get("saved_at")
            self.feed_latest_end = latest_end_raw
            metrics = payload.get('source_metrics')
            self.source_metrics = [item for item in metrics if isinstance(item, dict)] if isinstance(metrics, list) else []
            official = payload.get('official_metrics')
            if isinstance(official, dict):
                self.official_metrics = {**self.official_metrics, **official}
            print(
                "[TV Guide] Persistenter EPG-Cache sofort geladen: "
                f"{sum(1 for item in restored if item.get('available'))} von {len(restored)} Sendern",
                flush=True,
            )
            return True
        except Exception as exc:
            if self.parsed_cache_file.exists():
                print(f"[TV Guide] Persistenter EPG-Cache unbrauchbar: {exc}", flush=True)
            return False

    def _save_parsed_cache(self, source_url):
        try:
            payload = {
                "country": self.country,
                "schema_version": self.runtime.PARSED_CACHE_SCHEMA_VERSION,
                "saved_at": self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).isoformat(),
                "last_loaded": self.last_loaded,
                "source_url": source_url,
                "feed_latest_end": self.feed_latest_end,
                "source_metrics": self.source_metrics,
                "official_metrics": self.official_metrics,
                "channels": self.channels,
            }
            tmp = self.parsed_cache_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(tmp, self.parsed_cache_file)
            self.cache_schema_current = True
            write_catalogue(self.parsed_cache_file, self.country, self.channels)
        except Exception as exc:
            print(f"[TV Guide] Persistenter EPG-Cache konnte nicht gespeichert werden: {exc}", flush=True)

    def _candidate_urls(self):
        return list(self.source_urls)

    def _cache_fresh(self):
        if not self.cache_schema_current:
            return False
        if not self.source_metrics:
            return False
        # One stat call checks existence and age; avoid an extra exists()
        # filesystem operation on every maintenance check.
        try:
            age = time.time() - self.parsed_cache_file.stat().st_mtime
        except OSError:
            # The cache can disappear between exists() and stat() on cleanup.
            return False
        if age >= self.options["refresh_minutes"] * 60:
            return False
        # The following time-window check also rejects empty programme lists.
        # Avoid traversing all channels twice on each freshness check.
        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)
        if not any(
            self.runtime.datetime.fromisoformat(item["start"]) <= now < self.runtime.datetime.fromisoformat(item["end"])
            for channel in self.channels for item in channel.get("programs") or []
            if item.get("start") and item.get("end")
        ):
            return False
        return True

    def _download(self, url):
        attempts = [url]
        if url.endswith(".xml.gz"):
            attempts.append(url[:-3])

        last_error = None
        for candidate_url in attempts:
            req = Request(candidate_url, headers={
                "User-Agent": "HomeAssistant-TV-Guide/1.0",
                # XMLTV .gz files are already compressed. Request the transfer
                # unchanged so servers cannot wrap them in a second gzip layer.
                "Accept-Encoding": "identity",
            })
            download_tmp = self.cache_file.with_suffix(".download")
            cache_tmp = self.cache_file.with_suffix(".tmp")
            max_bytes = 100 * 1024 * 1024
            total = 0

            try:
                with self.runtime.urlopen(req, timeout=45) as response, download_tmp.open("wb") as target:
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("EPG-Datei ist größer als 100 MB.")
                        target.write(chunk)

                with download_tmp.open("rb") as source:
                    prefix = source.read(16)
                is_gzip = prefix[:2] == b"\x1f\x8b"

                if is_gzip:
                    os.replace(download_tmp, cache_tmp)
                else:
                    if not prefix.lstrip().startswith((b"<", b"<?xml")):
                        raise ValueError(
                            "EPG-Download ist weder XML noch GZIP-komprimiertes XMLTV."
                        )
                    with download_tmp.open("rb") as source, gzip.open(cache_tmp, "wb") as target:
                        while True:
                            chunk = source.read(256 * 1024)
                            if not chunk:
                                break
                            target.write(chunk)
                    download_tmp.unlink(missing_ok=True)

                os.replace(cache_tmp, self.cache_file)
                print(f"[TV Guide] Neuer EPG-Feed geladen: {candidate_url}", flush=True)
                return candidate_url
            except Exception as exc:
                last_error = exc
                print(
                    f"[TV Guide] EPG-Download fehlgeschlagen: {candidate_url} -> {exc}",
                    flush=True,
                )
            finally:
                download_tmp.unlink(missing_ok=True)
                cache_tmp.unlink(missing_ok=True)

        raise last_error or ValueError("EPG-Download fehlgeschlagen.")

    def _open_xml(self):
        with self.cache_file.open("rb") as source:
            is_gzip = source.read(2) == b"\x1f\x8b"
        return gzip.open(self.cache_file, "rb") if is_gzip else self.cache_file.open("rb")

    def refresh(self, force=False):
        with self.lock:
            self.refresh_running = True
            self.runtime.wake_sensors()
            self.last_refresh_attempt = time.time()
            self.options = self.runtime.load_options()
            errors = []

            try:
                if not force and self._cache_fresh():
                    self.last_error = None
                    return

                successful_sets = []
                successful_urls = []
                latest_end = None
                source_metrics = []

                candidate_urls = self._candidate_urls()
                for index, url in enumerate(candidate_urls, start=1):
                    if self.runtime.worker_stopped():
                        return
                    try:
                        print(
                            f"[TV Guide] Lade EPG-Quelle {index}/{len(candidate_urls)}: {url}",
                            flush=True,
                        )
                        self._download(url)
                        parsed_channels = self._parse()
                        self._validate_feed_quality(parsed_channels)
                        parsed_channels = self._tag_programmes(
                            parsed_channels,
                            url,
                            100 if url == self.runtime.EPGPW_EPG_URL else 220 if url == self.runtime.OPEN_EPG_URL else 210 if url == self.runtime.EPGSHARE_EPG_URL else 240,
                        )
                        successful_sets.append(parsed_channels)
                        successful_urls.append(url)

                        source_latest = (
                            self.runtime.datetime.fromisoformat(self.feed_latest_end)
                            if self.feed_latest_end else None
                        )
                        if source_latest and (latest_end is None or source_latest > latest_end):
                            latest_end = source_latest
                        source_metrics.append(
                            self._source_quality_metrics(
                                parsed_channels,
                                url,
                                source_latest,
                            )
                        )
                    except Exception as exc:
                        errors.append(f"{url}: {exc}")
                        source_metrics.append({
                            "url": url,
                            "ok": False,
                            "error": str(exc),
                            "channels": 0,
                            "available_channels": 0,
                            "main_channels": 0,
                            "programmes": 0,
                            "latest_end": None,
                        })
                        print(
                            f"[TV Guide] EPG-Quelle übersprungen: {url} -> {exc}",
                            flush=True,
                        )

                quarantined = self._quarantine_conflicting_fallback(successful_sets)
                for metric in source_metrics:
                    if metric.get("url") == self.runtime.EPGPW_EPG_URL:
                        metric["quarantined_channels"] = quarantined
                        fallback_sets = [channels for channels in successful_sets if any(
                            item.get("_source") == self.runtime.EPGPW_EPG_URL
                            for channel in channels for item in channel.get("programs") or []
                        )]
                        if quarantined and not fallback_sets:
                            metric.update(ok=False, error="Sendungsdaten widersprechen zwei übereinstimmenden Quellen.", programmes=0, available_channels=0, main_channels=0, latest_end=None)
                latest_end = max((
                    self.runtime.datetime.fromisoformat(item["end"])
                    for channels in successful_sets for channel in channels
                    for item in channel.get("programs") or [] if item.get("end")
                ), default=None)
                merged = self._merge_channel_sets(successful_sets)
                if not merged:
                    merged = [{**channel, "programs": [], "available": False, "preset": True}
                              for channel in self.catalog["channels"]]
                self.source_metrics = source_metrics
                if self.runtime.worker_stopped():
                    return
                supplemented = self._supplement_missing_channels(merged)
                if self.runtime.worker_stopped():
                    return
                if not any(channel.get("programs") for channel in supplemented):
                    self.last_error = " | ".join(errors) if errors else "Keine EPG-Quelle verfügbar."
                    print(f"[TV Guide] EPG-Fehler: {self.last_error}", flush=True)
                    return
                supplemented = self._retain_cached_programmes(supplemented)
                self.channels = supplemented
                latest_end = max((self.runtime.datetime.fromisoformat(item["end"])
                                  for channel in self.channels for item in channel.get("programs") or []), default=None)
                self.feed_latest_end = latest_end.isoformat() if latest_end else None
                self.last_loaded = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).isoformat()
                self.last_error = None
                self._save_parsed_cache("multi-source")

                coverage = self.coverage_metrics()
                preview = ", ".join(f"{day['date']}: {day['channels_with_evening_programmes']}/{coverage['main_channels']}"
                                    for day in coverage["days"])
                print(f"[TV Guide] Hauptsender-Abdeckung: jetzt {coverage['current_channels']}/{coverage['main_channels']}; "
                      f"Abendprogramme {preview}", flush=True)

                available = sum(1 for ch in self.channels if ch.get("available"))
                main_available = sum(
                    1 for ch in self.channels
                    if ch.get("preset") and ch.get("available")
                )
                print(
                    f"[TV Guide] EPG zusammengeführt: {len(successful_urls)} Quellen, "
                    f"{available} Sender mit Programmdaten, "
                    f"{main_available}/{len(self.catalog['channels'])} Hauptsender",
                    flush=True,
                )
                if errors:
                    print(
                        "[TV Guide] Einzelne EPG-Quellen fehlgeschlagen: "
                        + " | ".join(errors),
                        flush=True,
                    )
            finally:
                with self.runtime.SETTINGS_LOCK:
                    self.refresh_running = False
                    self.runtime.prune_country_stores()
                self.runtime.wake_sensors()

    def ensure_fresh_async(self):
        with self.runtime.SETTINGS_LOCK:
            # An HTTP request may still hold a store evicted during a country
            # switch. It can serve its snapshot but must not refresh it again.
            if self is not self.runtime.STORE and self.runtime.COUNTRY_STORES.get(self.country) is not self:
                return
            retry_due = (time.time() - self.last_refresh_attempt) >= 300
            # Avoid scanning programme data while a refresh is already running
            # or while the retry backoff has not elapsed.
            if self.refresh_running or not retry_due or self._cache_fresh():
                return
            self.refresh_running = True
        self.runtime.start_background(self.refresh)

    def payload(self, channel_ids=None):
        self.ensure_fresh_async()
        ui = self.runtime.load_options_ui()
        prefs = self.runtime.load_channel_preferences(self)
        by_id = {ch["id"]: ch for ch in self.channels}

        main_ids = [
            ch["id"]
            for ch in sorted(self.catalog["channels"], key=lambda x: x["order"])
            if ch["id"] in by_id
        ]
        hidden_ids = set(prefs["hidden"])
        custom_ids = [
            channel_id
            for channel_id in prefs["order"]
            if channel_id in by_id and channel_id not in hidden_ids
        ]

        if channel_ids is not None:
            main_ids = []
            custom_ids = [item for item in channel_ids if item in by_id]

        max_channels = ui.get("max_channels", 0) if channel_ids is None else 0
        if max_channels > 0:
            main_ids = main_ids[:max_channels]
            custom_ids = custom_ids[:max_channels]

        payload_ids = []
        for channel_id in [*main_ids, *custom_ids]:
            if channel_id in by_id and channel_id not in payload_ids:
                payload_ids.append(channel_id)

        channels = [dict(by_id[channel_id]) for channel_id in payload_ids]
        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)
        global_latest = (
            self.runtime.datetime.fromisoformat(self.feed_latest_end)
            if self.feed_latest_end else None
        )
        source_success = any(metric.get("ok") for metric in self.source_metrics) or bool(self.official_metrics.get("enriched"))

        for channel in channels:
            logo_light, logo_dark = self.runtime.normalized_logo_urls(channel)
            channel["logo_normalized_light"] = logo_light
            channel["logo_normalized_dark"] = logo_dark

            # Final output guard: never expose overlapping/duplicate programme
            # slots to the frontend, even when they came from an older cache
            # or from a provider parser that produced inconsistent intervals.
            programmes = self._validate_program_timeline(
                channel.get("programs") or []
            )
            cleaned_programmes = []
            for item in programmes:
                public_item = {
                    key: value
                    for key, value in item.items()
                    if not str(key).startswith("_")
                }
                public_item["source"] = item.get("_source_url") or item.get("_source")
                public_item["source_kind"] = item.get("_source_kind") or "unknown"
                cleaned_programmes.append(public_item)
            channel["programs"] = cleaned_programmes
            programmes = cleaned_programmes
            latest = None
            for item in programmes:
                try:
                    value = self.runtime.datetime.fromisoformat(item.get("end") or "")
                except Exception:
                    continue
                if latest is None or value > latest:
                    latest = value

            channel["data_latest_end"] = latest.isoformat() if latest else None
            if not programmes:
                if self.refresh_running:
                    channel["data_state"] = "loading"
                    channel["data_message"] = "Programmdaten werden gerade geladen."
                elif source_success:
                    channel["data_state"] = "no_programmes"
                    channel["data_message"] = "Für diesen Sender liegen aktuell keine Programmdaten vor."
                else:
                    channel["data_state"] = "source_unavailable"
                    channel["data_message"] = "Die Programmdatenquellen sind derzeit nicht erreichbar."
            elif latest and latest < now:
                channel["data_state"] = "ended"
                channel["data_message"] = "Die Programmdaten dieses Senders sind abgelaufen."
            elif global_latest and latest and latest < global_latest - timedelta(hours=6):
                channel["data_state"] = "ends_early"
                channel["data_message"] = "Die Programmdaten dieses Senders enden früher als bei den übrigen Sendern."
            else:
                channel["data_state"] = "ok"
                channel["data_message"] = ""

        return {
            "country": self.country,
            "country_name": self.runtime.COUNTRIES[self.country]["name"],
            "generated_at": self.runtime.datetime.now(self.runtime.EPG_TIMEZONE).isoformat(),
            "profile": self.catalog["profile"],
            "group": self.catalog["group"],
            "provider": "XMLTV",
            "source_url": "multi-source",
            "sources": self.source_urls,
            "source_metrics": self.source_metrics,
            "official_metrics": self.official_metrics,
            "coverage_metrics": self.coverage_metrics(),
            "official_provider_count": sum(
                1 for item in self.provider_audit.values() if item
            ),
            "official_provider_missing": [
                channel_id
                for channel_id, provider in self.provider_audit.items()
                if not provider
            ],
            "refresh_minutes": self.options["refresh_minutes"],
            "ui": {
                "language": self.runtime.load_options().get("language", "auto"),
                "home_assistant": self.runtime.home_assistant_locale(),
                "default_view": ui.get("default_view", "now"),
                "columns_desktop": ui.get("columns_desktop", 5),
                "max_channels": ui.get("max_channels", 0),
                "theme_mode": ui.get("theme_mode", "auto"),
            },
            "last_loaded": self.last_loaded,
            "feed_latest_end": self.feed_latest_end,
            "error": self.last_error,
            "refresh_running": self.refresh_running,
            "persistent_cache": self.parsed_cache_file.exists(),
            "channel_preferences": prefs,
            "main_channel_ids": main_ids,
            "custom_channel_ids": custom_ids,
            "channels": channels,
        }

