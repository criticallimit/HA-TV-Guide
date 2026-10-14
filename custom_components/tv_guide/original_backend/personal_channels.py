"""A personal selection across independent country catalogues and EPG stores."""
import threading

from .cache_catalogue import read_catalogue
from .json_files import read_json_file, write_json_file


class PersonalChannels:
    def __init__(self, runtime):
        self.runtime = runtime
        self.lock = threading.RLock()

    @property
    def path(self):
        return self.runtime.CHANNEL_PREFS_FILE.with_name("tv_guide_personal_channels.json")

    def country_store(self, country):
        with self.runtime.SETTINGS_LOCK:
            if self.runtime.STORE.country == country:
                return self.runtime.STORE
            if country not in self.runtime.COUNTRY_STORES:
                self.runtime.COUNTRY_STORES[country] = self.runtime.EPGStore(country)
            self.runtime.prune_country_stores(keep={country})
            return self.runtime.COUNTRY_STORES[country]

    def load(self, store):
        with self.lock:
            saved = read_json_file(self.path, {})
            if isinstance(saved.get("order"), list):
                order = list(dict.fromkeys(item for item in saved["order"] if isinstance(item, str)))
                countries = saved.get("countries")
                countries = countries if isinstance(countries, list) else [store.country]
                return {"order": order, "countries": [code for code in self.runtime.COUNTRIES if code in countries]}
            # Until the first save, retain the existing active-country selection.
            # Never rewrite or remove the original per-country preference files.
            prefs = self.runtime.load_channel_preferences(store)
            hidden = set(prefs["hidden"])
            return {
                "order": [f"{store.country}:{item}" for item in prefs["order"] if item not in hidden],
                "countries": [store.country],
            }

    def catalogue(self, store):
        with self.runtime.SETTINGS_LOCK:
            stores = dict(self.runtime.COUNTRY_STORES)
        stores[store.country] = store
        result = {}
        for country in self.runtime.COUNTRIES:
            catalog = self.runtime.CHANNELS if country == "de" else self.runtime.COUNTRY_CATALOGS[country]
            channels = {item["id"]: item for item in catalog["channels"]}
            # Cached additional feed channels remain selectable after a restart.
            cached_path = self.runtime.country_file(self.runtime.PARSED_CACHE_FILE, country)
            if country in stores:
                channels.update({item["id"]: item for item in stores[country].channels})
            else:
                channels.update({item["id"]: item for item in read_catalogue(cached_path, country)})
            for channel_id, item in channels.items():
                key = f"{country}:{channel_id}"
                result[key] = {
                    **item, "id": key, "source_channel_id": channel_id,
                    "source_country": country, "country_name": self.runtime.COUNTRIES[country]["name"],
                }
        return result

    def logo_channel(self, key):
        country, separator, channel_id = key.partition(":")
        if not separator or country not in self.runtime.COUNTRIES:
            return None
        catalog = self.runtime.CHANNELS if country == "de" else self.runtime.COUNTRY_CATALOGS[country]
        channel = next((item for item in catalog["channels"] if item["id"] == channel_id), None)
        if channel is None:
            channel = next((item for item in self.country_store(country).channels if item["id"] == channel_id), None)
        return {**channel, "id": key, "source_channel_id": channel_id} if channel else None

    def settings(self, store):
        prefs = self.load(store)
        channels = self.catalogue(store)
        return {
            **prefs,
            "country": store.country,
            "supported_countries": [{"code": code, "name": item["name"]} for code, item in self.runtime.COUNTRIES.items()],
            "channels": [{
                "id": item["id"], "name": item["name"],
                "source_country": item["source_country"], "country_name": item["country_name"],
                "logo_normalized_light": self.runtime.normalized_logo_urls(item)[0],
                "logo_normalized_dark": self.runtime.normalized_logo_urls(item)[1],
            } for item in channels.values()],
        }

    def save(self, order, countries, store):
        if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
            raise ValueError("Ungültige Sender-IDs.")
        if not isinstance(countries, list) or not all(isinstance(code, str) and code in self.runtime.COUNTRIES for code in countries):
            raise ValueError("Ungültiges Land.")
        known = self.catalogue(store)
        if any(item not in known for item in order):
            raise ValueError("Ungültige Sender-IDs.")
        prefs = {"order": list(dict.fromkeys(order)), "countries": list(dict.fromkeys(countries))}
        with self.lock:
            write_json_file(self.path, {"version": 1, **prefs})
        with self.runtime.SETTINGS_LOCK:
            self.runtime.prune_country_stores()
        return prefs

    def reset(self, store):
        return self.save([f"{store.country}:{item}" for item in self.runtime.base_channel_ids(store)], [store.country], store)

    def guide(self, store):
        payload = store.payload()
        prefs = self.load(store)
        maximum = payload["ui"].get("max_channels", 0)
        order = prefs["order"][:maximum] if maximum > 0 else prefs["order"]
        groups = {}
        for key in order:
            country, separator, channel_id = key.partition(":")
            if separator and country in self.runtime.COUNTRIES:
                groups.setdefault(country, []).append(channel_id)
        personal = {}
        latest_ends = [payload["feed_latest_end"]] if payload["feed_latest_end"] else []
        for country, ids in groups.items():
            current_channels = {item["id"] for item in payload["channels"]}
            country_payload = (payload if country == store.country and all(item in current_channels for item in ids)
                               else self.country_store(country).payload(channel_ids=ids))
            payload["refresh_running"] |= country_payload["refresh_running"]
            if country_payload["feed_latest_end"]:
                latest_ends.append(country_payload["feed_latest_end"])
            requested = set(ids)
            for item in country_payload["channels"]:
                if item["id"] not in requested:
                    continue
                key = f"{country}:{item['id']}"
                channel = {**item, "id": key, "source_channel_id": item["id"], "source_country": country,
                           "country_name": self.runtime.COUNTRIES[country]["name"]}
                light, dark = self.runtime.normalized_logo_urls(channel)
                channel.update(logo_normalized_light=light, logo_normalized_dark=dark)
                personal[key] = channel
        payload["channels"] = [item for item in payload["channels"] if item["id"] in payload["main_channel_ids"]] + list(personal.values())
        payload["custom_channel_ids"] = [key for key in order if key in personal]
        payload["personal_channel_preferences"] = prefs
        payload["feed_latest_end"] = max(latest_ends, key=self.runtime.datetime.fromisoformat) if latest_ends else None
        return payload
