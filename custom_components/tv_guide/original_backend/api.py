"""HTTP routes for the guide, settings, reminders and bookmarks.


The application context is supplied by services.py; all mutable state is shared.
"""

import json
import re
import threading
from datetime import timedelta
from http.server import SimpleHTTPRequestHandler
from urllib.parse import unquote, urlparse

from .json_files import read_json_file


class GuideRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Revalidate the entry page so updates cannot keep an obsolete settings UI.
        path = urlparse(self.path).path
        if path.endswith("/") or path.endswith(".html"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def translate_path(self, path):
        raw = urlparse(path).path
        rel = raw.lstrip("/") or "index.html"
        candidate = (self.runtime.WWW / rel).resolve()
        root = self.runtime.WWW.resolve()
        if candidate == root or root in candidate.parents:
            return str(candidate)
        return str(root / "__invalid_path__")

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        store = self.runtime.STORE
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if "/api/channel-logo/" in path:
            match = re.search(r"/api/channel-logo/([^/]+)/(light|dark)\.svg$", path)
            if not match:
                self.send_error(404)
                return
            channel_id = unquote(match.group(1))
            theme = match.group(2)
            channel = next((item for item in store.channels if item.get("id") == channel_id), None)
            if not channel and ":" in channel_id:
                channel = self.runtime.PERSONAL_CHANNELS.logo_channel(channel_id)
            if not channel:
                self.send_error(404)
                return
            data = self.runtime.normalized_logo_data(channel, theme)
            if not data:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.endswith("/api/guide") or path == "/api/guide":
            return self._json(self.runtime.PERSONAL_CHANNELS.guide(store))
        if path.endswith("/api/channels") or path == "/api/channels":
            return self._json(store.catalog)
        if path.endswith("/api/personal-channels"):
            return self._json(self.runtime.PERSONAL_CHANNELS.settings(store))
        if path.endswith("/api/channel-settings") or path == "/api/channel-settings":
            prefs = self.runtime.load_channel_preferences(store)
            selected = set(prefs["order"])
            hidden = set(prefs["hidden"])
            channel_info = [
                {
                    "id": ch["id"],
                    "logo_normalized_light": self.runtime.normalized_logo_urls(ch)[0],
                    "logo_normalized_dark": self.runtime.normalized_logo_urls(ch)[1],
                    "name": ch["name"],
                    "logo_file": ch.get("logo_file"),
                    "logo_file_light": ch.get("logo_file_light"),
                    "logo": ch.get("logo"),
                    "logo_light": ch.get("logo_light"),
                    "logo_dark": ch.get("logo_dark"),
                    "base_order": ch.get("order", 99999),
                    "preset": bool(ch.get("preset")),
                    "catalog_group": ch.get("catalog_group") or "Weitere Sender",
                    "available": bool(ch.get("available")),
                    "source_id": ch.get("source_id"),
                    "selected": ch["id"] in selected and ch["id"] not in hidden,
                }
                for ch in store.channels
            ]
            channel_info.sort(key=lambda ch: (
                0 if ch["selected"] else 1,
                0 if ch["preset"] else 1,
                ch["base_order"] if ch["preset"] else 99999,
                ch["name"].casefold(),
            ))
            return self._json({
                **prefs,
                "channels": channel_info,
                "catalog_count": len(channel_info),
                "country": store.country,
            })
        if path.endswith("/api/settings") or path == "/api/settings":
            ui = self.runtime.load_options_ui()
            options = self.runtime.load_options()
            return self._json({
                "country": store.country,
                "language": options["language"],
                "home_assistant": self.runtime.home_assistant_locale(wait=False),
                "countries": [{"code": code, "name": item["name"]} for code, item in self.runtime.COUNTRIES.items()],
                "default_view": ui["default_view"],
                "columns_desktop": ui["columns_desktop"],
                "max_channels": ui["max_channels"],
                "theme_mode": ui["theme_mode"],
                "refresh_minutes": options["refresh_minutes"],
                "notification_service": options["notification_service"],
                **{key: options[key] for key in self.runtime.SENSOR_OPTIONS},
            })
        if path.endswith("/api/notification-services") or path == "/api/notification-services":
            return self._json({"services": self.runtime.list_notification_services()})
        if path.endswith("/api/reminders") or path == "/api/reminders":
            with self.runtime.REMINDER_LOCK:
                return self._json({"reminders": self.runtime.load_reminders()})
        if path.endswith("/api/bookmarks") or path == "/api/bookmarks":
            with self.runtime.BOOKMARK_LOCK:
                stored_bookmarks = self.runtime.load_bookmarks()
                bookmarks = self.runtime.clean_bookmarks(stored_bookmarks)
                if bookmarks != stored_bookmarks:
                    self.runtime.save_bookmarks(bookmarks)
                return self._json({"bookmarks": bookmarks})
        if path.endswith("/api/status") or path == "/api/status":
            return self._json({
                "provider": "XMLTV",
                "source_url": "multi-source",
                "sources": store.source_urls,
                "source_metrics": store.source_metrics,
                "official_metrics": store.official_metrics,
                "coverage_metrics": store.coverage_metrics(),
                "official_provider_count": sum(
                    1 for item in store.provider_audit.values() if item
                ),
                "official_provider_missing": [
                    channel_id
                    for channel_id, provider in store.provider_audit.items()
                    if not provider
                ],
                "last_loaded": store.last_loaded,
                "feed_latest_end": store.feed_latest_end,
                "error": store.last_error,
                "cache_exists": store.parsed_cache_file.exists(),
                "refresh_running": store.refresh_running,
            })
        if path.endswith("/api/refresh") or path == "/api/refresh":
            store.refresh(force=True)
            return self._json({"ok": store.last_error is None, "error": store.last_error})
        return super().do_GET()

    def do_POST(self):
        store = self.runtime.STORE
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > 65536:
                return self._json({"ok": False, "error": "Ungültige Anfrage."}, status=400)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))

            if path.endswith("/api/personal-channels"):
                try:
                    prefs = (self.runtime.PERSONAL_CHANNELS.reset(store) if payload.get("reset") else
                             self.runtime.PERSONAL_CHANNELS.save(payload.get("order"), payload.get("countries"), store))
                except ValueError as exc:
                    return self._json({"ok": False, "error": str(exc)}, status=400)
                return self._json({"ok": True, **prefs})

            if path.endswith("/api/channel-settings") or path == "/api/channel-settings":
                if payload.get("country", store.country) != store.country:
                    return self._json({"ok": False, "error": "Das Land wurde geändert. Bitte die Senderliste erneut öffnen."}, status=409)
                if payload.get("reset"):
                    prefs = self.runtime.reset_channel_preferences(store)
                else:
                    order = payload.get("order")
                    hidden = payload.get("hidden")
                    if not isinstance(order, list) or not isinstance(hidden, list):
                        return self._json({"ok": False, "error": "Ungültige Senderkonfiguration."}, status=400)
                    if not all(isinstance(x, str) for x in order + hidden):
                        return self._json({"ok": False, "error": "Ungültige Sender-IDs."}, status=400)
                    prefs = self.runtime.save_channel_preferences(order, hidden, store)
                return self._json({"ok": True, **prefs})

            if path.endswith("/api/settings") or path == "/api/settings":
                current_raw = read_json_file(self.runtime.OPTIONS_FILE, {})

                country = str(payload.get("country", store.country)).lower()
                if country not in self.runtime.COUNTRIES:
                    return self._json({"ok": False, "error": "Ungültiges Land."}, status=400)
                language = str(payload.get("language", current_raw.get("language", "auto"))).lower()
                if language not in self.runtime.LANGUAGES | {"auto"}:
                    return self._json({"ok": False, "error": "Ungültige Sprache."}, status=400)
                default_view = str(payload.get("default_view") or "now")
                if default_view not in {"now", "1800", "2015", "2200"}:
                    return self._json({"ok": False, "error": "Ungültige Standardansicht."}, status=400)

                try:
                    columns = int(payload.get("columns_desktop"))
                    max_channels = int(payload.get("max_channels"))
                    refresh_minutes = int(payload.get("refresh_minutes"))
                except Exception:
                    return self._json({"ok": False, "error": "Ungültige Zahlenwerte."}, status=400)

                if columns < 3 or columns > 6:
                    return self._json({"ok": False, "error": "Sender pro Reihe muss zwischen 3 und 6 liegen."}, status=400)
                if max_channels < 0 or max_channels > 500:
                    return self._json({"ok": False, "error": "Angezeigte Sender muss zwischen 0 und 500 liegen."}, status=400)
                if refresh_minutes < 30 or refresh_minutes > 1440:
                    return self._json({"ok": False, "error": "EPG-Aktualisierung muss zwischen 30 und 1440 Minuten liegen."}, status=400)

                theme_mode = str(payload.get("theme_mode") or "auto").lower()
                if theme_mode not in {"auto", "dark", "light"}:
                    return self._json({"ok": False, "error": "Ungültige Darstellung."}, status=400)

                notification_service = str(payload.get("notification_service") or "").strip().lower()
                if not re.match(r"^[a-z0-9_]+\.[a-z0-9_]+$", notification_service):
                    return self._json({"ok": False, "error": "Ungültiger Benachrichtigungsdienst."}, status=400)

                try:
                    current_refresh_minutes = int(
                        current_raw.get("refresh_minutes") or self.runtime.DEFAULT_REFRESH_MINUTES
                    )
                except Exception:
                    current_refresh_minutes = self.runtime.DEFAULT_REFRESH_MINUTES

                refresh_needed = refresh_minutes != current_refresh_minutes
                sensor_options = {key: payload.get(key, current_raw.get(key, False)) for key in self.runtime.SENSOR_OPTIONS}
                if not all(isinstance(value, bool) for value in sensor_options.values()):
                    return self._json({"ok": False, "error": "Ungültige Sensor-Einstellung."}, status=400)

                new_options = {
                    "country": country,
                    "language": language,
                    "default_view": default_view,
                    "columns_desktop": columns,
                    "max_channels": max_channels,
                    "theme_mode": theme_mode,
                    "refresh_minutes": refresh_minutes,
                    "notification_service": notification_service,
                    **sensor_options,
                }
                with self.runtime.SETTINGS_LOCK:
                    self.runtime.update_addon_options(new_options)
                    self.runtime.save_options_file(new_options)
                    country_changed = country != self.runtime.STORE.country
                    if country_changed:
                        if country not in self.runtime.COUNTRY_STORES:
                            self.runtime.COUNTRY_STORES[country] = self.runtime.EPGStore(country)
                        self.runtime.STORE = self.runtime.COUNTRY_STORES[country]
                    self.runtime.STORE.options = self.runtime.load_options()
                    self.runtime.prune_country_stores()
                    refresh_needed = refresh_needed or country_changed
                    if refresh_needed and not self.runtime.STORE.refresh_running:
                        self.runtime.STORE.refresh_running = True
                        self.runtime.start_background(self.runtime.STORE.refresh, force=True)

                self.runtime.wake_sensors()
                return self._json({
                    "ok": True,
                    "country": country,
                    "country_changed": country_changed,
                    "refresh_started": bool(refresh_needed),
                })

            if path.endswith("/api/reminders") or path == "/api/reminders":
                action = str(payload.get("action") or "")
                reminder_id = str(payload.get("id") or "").strip()
                if not reminder_id:
                    return self._json({"ok": False, "error": "Erinnerungs-ID fehlt."}, status=400)

                with self.runtime.REMINDER_LOCK:
                    reminders = self.runtime.load_reminders()
                    reminders = [item for item in reminders if item.get("id") != reminder_id]

                    if action == "upsert":
                        minutes = int(payload.get("minutes") or 10)
                        if minutes not in {5, 10, 15, 30}:
                            return self._json({"ok": False, "error": "Ungültiger Erinnerungszeitpunkt."}, status=400)

                        start_raw = str(payload.get("start") or "")
                        end_raw = str(payload.get("end") or "")
                        start = self.runtime.datetime.fromisoformat(start_raw).astimezone(self.runtime.EPG_TIMEZONE)
                        end = self.runtime.datetime.fromisoformat(end_raw).astimezone(self.runtime.EPG_TIMEZONE)
                        now = self.runtime.datetime.now(self.runtime.EPG_TIMEZONE)
                        if end <= start or end <= now or start <= now:
                            return self._json({"ok": False, "error": "Für bereits laufende oder beendete Sendungen ist keine Erinnerung möglich."}, status=400)

                        reminders.append({
                            "id": reminder_id,
                            "channel": str(payload.get("channel") or "Unbekannter Sender")[:120],
                            "channelId": str(payload.get("channelId") or "")[:120],
                            "title": str(payload.get("title") or "Sendung")[:240],
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                            "minutes": minutes,
                            "language": self.runtime.effective_language(payload.get("language")),
                            "sent": False,
                        })
                    elif action != "remove":
                        return self._json({"ok": False, "error": "Unbekannte Erinnerungsaktion."}, status=400)

                    reminders.sort(key=lambda item: item.get("start", ""))
                    self.runtime.save_reminders(reminders)
                    return self._json({"ok": True, "reminders": reminders})

            if path.endswith("/api/test-notification") or path == "/api/test-notification":
                test = {
                    "id": "tv_guide_test",
                    "channel": "TV Guide",
                    "title": self.runtime.translate("Testbenachrichtigung", self.runtime.effective_language(payload.get("language"))),
                    "language": self.runtime.effective_language(payload.get("language")),
                    "start": (self.runtime.datetime.now(self.runtime.EPG_TIMEZONE) + timedelta(minutes=1)).isoformat(),
                    "end": (self.runtime.datetime.now(self.runtime.EPG_TIMEZONE) + timedelta(minutes=2)).isoformat(),
                    "minutes": 1,
                }
                self.runtime._ha_notification(test)
                return self._json({
                    "ok": True,
                    "service": self.runtime.load_options().get("notification_service", "persistent_notification.create"),
                })

            if path.endswith("/api/bookmarks") or path == "/api/bookmarks":
                action = str(payload.get("action") or "")
                bookmark_id = str(payload.get("id") or "").strip()
                if not bookmark_id:
                    return self._json({"ok": False, "error": "Merklisten-ID fehlt."}, status=400)

                with self.runtime.BOOKMARK_LOCK:
                    bookmarks = self.runtime.clean_bookmarks(self.runtime.load_bookmarks())
                    bookmarks = [item for item in bookmarks if item.get("id") != bookmark_id]

                    if action == "upsert":
                        start_raw = str(payload.get("start") or "")
                        end_raw = str(payload.get("end") or "")
                        start = self.runtime.datetime.fromisoformat(start_raw).astimezone(self.runtime.EPG_TIMEZONE)
                        end = self.runtime.datetime.fromisoformat(end_raw).astimezone(self.runtime.EPG_TIMEZONE)
                        if end <= start or end <= self.runtime.datetime.now(self.runtime.EPG_TIMEZONE):
                            return self._json({"ok": False, "error": "Beendete Sendungen können nicht gemerkt werden."}, status=400)
                        bookmarks.append({
                            "id": bookmark_id,
                            "channel": str(payload.get("channel") or "Unbekannter Sender")[:120],
                            "channelId": str(payload.get("channelId") or "")[:120],
                            "title": str(payload.get("title") or "Sendung")[:240],
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                        })
                    elif action != "remove":
                        return self._json({"ok": False, "error": "Unbekannte Merklistenaktion."}, status=400)

                    bookmarks.sort(key=lambda item: item.get("start", ""))
                    self.runtime.save_bookmarks(bookmarks)

                    if action == "remove":
                        with self.runtime.REMINDER_LOCK:
                            reminders = self.runtime.load_reminders()
                            remaining = [
                                item for item in reminders
                                if item.get("id") != bookmark_id
                            ]
                            if remaining != reminders:
                                self.runtime.save_reminders(remaining)

                    return self._json({"ok": True, "bookmarks": bookmarks})

            return self._json({"ok": False, "error": "Nicht gefunden."}, status=404)
        except Exception as exc:
            return self._json({"ok": False, "error": str(exc)}, status=400)

    def log_request(self, code="-", size="-"):
        try:
            if 200 <= int(code) < 400:
                return
        except (TypeError, ValueError):
            pass
        super().log_request(code, size)

    def log_message(self, fmt, *args):
        print("[TV Guide]", fmt % args, flush=True)

