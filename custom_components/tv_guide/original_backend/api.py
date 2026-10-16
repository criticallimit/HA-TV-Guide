"""Direct operations for the native programme engine and presentation settings.


The application context is supplied by services.py; all mutable state is shared.
"""

import re



class GuideOperations:
    """Dispatch programme operations; the native caller supplies JSON capture."""

    def __init__(self, runtime):
        self.runtime = runtime

    def _result(self, payload, status=200):
        if status >= 400:
            raise ValueError(payload.get("error", "TV Guide request failed"))
        return payload


    def get(self, endpoint):
        store = self.runtime.STORE
        if endpoint == "guide":
            return self._result(self.runtime.PERSONAL_CHANNELS.guide(store))
        if endpoint == "channels":
            return self._result(store.catalog)
        if endpoint == "personal-channels":
            return self._result(self.runtime.PERSONAL_CHANNELS.settings(store))
        if endpoint == "channel-settings":
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
            return self._result({
                **prefs,
                "channels": channel_info,
                "catalog_count": len(channel_info),
                "country": store.country,
            })
        if endpoint == "settings":
            ui = self.runtime.load_options_ui()
            options = self.runtime.load_options()
            return self._result({
                "country": store.country,
                "language": options["language"],
                "country_language": ui["country_language"],
                "home_assistant": self.runtime.home_assistant_locale(),
                "countries": [{"code": code, "name": item["name"], "language": item.get("language")} for code, item in self.runtime.COUNTRIES.items()],
                "default_view": ui["default_view"],
                "columns_desktop": ui["columns_desktop"],
                "max_channels": ui["max_channels"],
                "theme_mode": ui["theme_mode"],
                "refresh_minutes": options["refresh_minutes"],
                "notification_service": options["notification_service"],
            })
        if endpoint == "status":
            return self._result({
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
        if endpoint == "refresh":
            store.refresh(force=True)
            return self._result({"ok": store.last_error is None, "error": store.last_error})
        raise ValueError("Unsupported in-process guide route")

    def post(self, endpoint, payload):
        store = self.runtime.STORE

        try:
            if endpoint == "personal-channels":
                try:
                    prefs = (self.runtime.PERSONAL_CHANNELS.reset(store) if payload.get("reset") else
                             self.runtime.PERSONAL_CHANNELS.save(payload.get("order"), payload.get("countries"), store))
                except ValueError as exc:
                    return self._result({"ok": False, "error": str(exc)}, status=400)
                return self._result({"ok": True, **prefs})

            if endpoint == "channel-settings":
                if payload.get("country", store.country) != store.country:
                    return self._result({"ok": False, "error": "Das Land wurde geändert. Bitte die Senderliste erneut öffnen."}, status=409)
                if payload.get("reset"):
                    prefs = self.runtime.reset_channel_preferences(store)
                else:
                    order = payload.get("order")
                    hidden = payload.get("hidden")
                    if not isinstance(order, list) or not isinstance(hidden, list):
                        return self._result({"ok": False, "error": "Ungültige Senderkonfiguration."}, status=400)
                    if not all(isinstance(x, str) for x in order + hidden):
                        return self._result({"ok": False, "error": "Ungültige Sender-IDs."}, status=400)
                    prefs = self.runtime.save_channel_preferences(order, hidden, store)
                return self._result({"ok": True, **prefs})

            if endpoint == "settings":
                current_raw = self.runtime.settings.read(self.runtime.OPTIONS_FILE)

                country = str(payload.get("country", store.country)).lower()
                if country not in self.runtime.COUNTRIES:
                    return self._result({"ok": False, "error": "Ungültiges Land."}, status=400)
                language = str(payload.get("language", current_raw.get("language", "auto"))).lower()
                if language not in self.runtime.LANGUAGES | {"auto"}:
                    return self._result({"ok": False, "error": "Ungültige Sprache."}, status=400)
                default_view = str(payload.get("default_view") or "now")
                if default_view not in {"now", "1800", "2015", "2200"}:
                    return self._result({"ok": False, "error": "Ungültige Standardansicht."}, status=400)

                try:
                    columns = int(payload.get("columns_desktop"))
                    max_channels = int(payload.get("max_channels"))
                    refresh_minutes = int(payload.get("refresh_minutes"))
                except Exception:
                    return self._result({"ok": False, "error": "Ungültige Zahlenwerte."}, status=400)

                if columns < 3 or columns > 6:
                    return self._result({"ok": False, "error": "Sender pro Reihe muss zwischen 3 und 6 liegen."}, status=400)
                if max_channels < 0 or max_channels > 500:
                    return self._result({"ok": False, "error": "Angezeigte Sender muss zwischen 0 und 500 liegen."}, status=400)
                if refresh_minutes < 30 or refresh_minutes > 1440:
                    return self._result({"ok": False, "error": "EPG-Aktualisierung muss zwischen 30 und 1440 Minuten liegen."}, status=400)

                theme_mode = str(payload.get("theme_mode") or "auto").lower()
                if theme_mode not in {"auto", "dark", "light"}:
                    return self._result({"ok": False, "error": "Ungültige Darstellung."}, status=400)

                notification_service = str(payload.get("notification_service") or "").strip().lower()
                if not re.match(r"^[a-z0-9_]+\.[a-z0-9_]+$", notification_service):
                    return self._result({"ok": False, "error": "Ungültiger Benachrichtigungsdienst."}, status=400)

                new_options = {
                    "country": country,
                    "language": language,
                    "default_view": default_view,
                    "columns_desktop": columns,
                    "max_channels": max_channels,
                    "theme_mode": theme_mode,
                    "refresh_minutes": refresh_minutes,
                    "notification_service": notification_service,
                }
                with self.runtime.SETTINGS_LOCK:
                    self.runtime.save_options_file(new_options)
                    country_changed = country != self.runtime.STORE.country
                    if country_changed:
                        if country not in self.runtime.COUNTRY_STORES:
                            self.runtime.COUNTRY_STORES[country] = self.runtime.EPGStore(country, load_cache=False)
                        self.runtime.STORE = self.runtime.COUNTRY_STORES[country]
                    self.runtime.STORE.options = self.runtime.load_options()
                    self.runtime.prune_country_stores()
                    refresh_needed = country_changed
                    if refresh_needed and not self.runtime.STORE.refresh_running:
                        self.runtime.STORE.refresh_running = True
                        selected = self.runtime.STORE
                        if selected._cache_pending:
                            selected.refresh_running = False
                            self.runtime.restore_country(selected)
                        else:
                            self.runtime.start_background(selected.refresh)

                self.runtime.wake_sensors(programmes=False, routing=country_changed)
                return self._result({
                    "ok": True,
                    "country": country,
                    "country_changed": country_changed,
                    "refresh_started": bool(refresh_needed),
                    "settings": new_options,
                })

            return self._result({"ok": False, "error": "Nicht gefunden."}, status=404)
        except Exception as exc:
            return self._result({"ok": False, "error": str(exc)}, status=400)
