import html
import json
import re
import sys
import threading
from datetime import datetime
from urllib.request import urlopen

from .api import GuideRequestHandler
from .json_files import read_json_file, write_json_file
from .personal_channels import PersonalChannels
from .programme_values import EPG_TIMEZONE as EPG_TIMEZONE
from .programme_values import feed_channel_id as feed_channel_id
from .programme_values import first_text as first_text
from .programme_values import normalize as normalize
from .programme_values import xmltv_datetime as xmltv_datetime
from .providers import ARD_PROGRAM_URL as ARD_PROGRAM_URL
from .providers import ARD_RB_PROGRAM_URL as ARD_RB_PROGRAM_URL
from .providers import BUILTIN_EPG_URLS as BUILTIN_EPG_URLS
from .providers import EPGPW_EPG_URL as EPGPW_EPG_URL
from .providers import EPGSHARE_EPG_URL as EPGSHARE_EPG_URL
from .providers import OFFICIAL_PROVIDER_BY_CHANNEL as OFFICIAL_PROVIDER_BY_CHANNEL
from .providers import OPEN_EPG_URL as OPEN_EPG_URL
from .providers import (
    SECONDARY_WEB_PROVIDER_BY_CHANNEL as SECONDARY_WEB_PROVIDER_BY_CHANNEL,
)
from .providers import SR_PROGRAM_URL as SR_PROGRAM_URL
from .providers import SWR_PROGRAM_URL as SWR_PROGRAM_URL
from .providers import TELETEXT_PROVIDER_BY_CHANNEL as TELETEXT_PROVIDER_BY_CHANNEL
from .providers import ZDF_PROGRAM_URL as ZDF_PROGRAM_URL
from .store import GuideStore

BASE = GUIDE_ASSET_ROOT
CHANNELS = json.loads((BASE / "data" / "channels.json").read_text(encoding="utf-8"))
COUNTRIES = json.loads((BASE / "data" / "countries.json").read_text(encoding="utf-8"))
COUNTRY_CATALOGS = {
    code: json.loads((BASE / "data" / item["catalog"]).read_text(encoding="utf-8"))
    for code, item in COUNTRIES.items() if code != "de"
}
LOGO_LIBRARY = json.loads((BASE / "data" / "logo_library.json").read_text(encoding="utf-8"))
LOGO_UPDATES_FILE = BASE / "data" / "logo_updates.json"
if LOGO_UPDATES_FILE.is_file():
    for logo_part in json.loads(LOGO_UPDATES_FILE.read_text(encoding="utf-8"))["library_parts"]:
        logo_additions = json.loads((BASE / "data" / logo_part).read_text(encoding="utf-8"))
        LOGO_LIBRARY["channels"].update(logo_additions["channels"])
        LOGO_LIBRARY["assets"].update(logo_additions["assets"])
EUROPE_LOGO_LIBRARY_FILE = BASE / "data" / "europe_logo_library.json"
EUROPE_LOGO_LIBRARY = (
    json.loads(EUROPE_LOGO_LIBRARY_FILE.read_text(encoding="utf-8"))
    if EUROPE_LOGO_LIBRARY_FILE.is_file()
    else {"assets": {}, "aliases": {}}
)
OPTIONS_FILE = GUIDE_STORAGE_ROOT / "options.json"
CACHE_FILE = GUIDE_STORAGE_ROOT / "tv_guide_epg.xml.gz"
PARSED_CACHE_FILE = GUIDE_STORAGE_ROOT / "tv_guide_epg_parsed.json"
PARSED_CACHE_SCHEMA_VERSION = 10
CHANNEL_PREFS_FILE = GUIDE_STORAGE_ROOT / "tv_guide_channel_order.json"


# Every curated main channel goes through the same official-source layer. Channels
# without a stable public schedule endpoint remain XMLTV-only until a verified
# official endpoint is added here; no guessed URLs are used.
OFFICIAL_PROVIDER_AUDIT = {
    channel_id: OFFICIAL_PROVIDER_BY_CHANNEL.get(channel_id)
    for channel_id in [ch["id"] for ch in CHANNELS["channels"]]
}


DEFAULT_REFRESH_MINUTES = 180

LANGUAGES = {"da", "de", "en", "nl", "fr", "it", "nb", "sv"}
def home_assistant_locale():
    return dict(GUIDE_LOCALE)


def save_options_file(options):
    write_json_file(OPTIONS_FILE, options)


def country_code(value):
    value = str(value or "de").lower()
    return value if value in COUNTRIES else "de"


def country_file(path, country):
    # Preserve every existing German installation's file paths.
    return path if country == "de" else path.with_name(f"{country}_{path.name}")


def active_store(store=None):
    return store if store is not None else globals().get("STORE")


def channel_catalog(store=None):
    store = active_store(store)
    return store.catalog if store is not None else CHANNELS


def channel_preferences_file(store=None):
    store = active_store(store)
    return country_file(CHANNEL_PREFS_FILE, getattr(store, "country", "de"))


def load_options():
    data = read_json_file(OPTIONS_FILE, {})
    try:
        refresh = int(data.get("refresh_minutes") or DEFAULT_REFRESH_MINUTES)
    except Exception:
        refresh = DEFAULT_REFRESH_MINUTES
    notification_service = str(
        data.get("notification_service") or "persistent_notification.create"
    ).strip().lower()
    if not re.match(r"^[a-z0-9_]+\.[a-z0-9_]+$", notification_service):
        notification_service = "persistent_notification.create"
    language = data.get("language")
    return {
        "country": country_code(data.get("country")),
        "language": language if isinstance(language, str) and language in LANGUAGES | {"auto"} else "auto",
        "refresh_minutes": max(30, min(1440, refresh)),
        "notification_service": notification_service,
    }

def load_options_ui():
    data = read_json_file(OPTIONS_FILE, {})
    default_view = str(data.get("default_view") or "now")
    if default_view not in {"now", "1800", "2015", "2200"}:
        default_view = "now"
    try:
        columns = int(data.get("columns_desktop") or 5)
    except Exception:
        columns = 5
    try:
        max_channels = int(data.get("max_channels") or 0)
    except Exception:
        max_channels = 0
    theme_mode = str(data.get("theme_mode") or "auto").lower()
    if theme_mode not in {"auto", "dark", "light"}:
        theme_mode = "auto"
    return {
        "default_view": default_view,
        "columns_desktop": max(3, min(6, columns)),
        "max_channels": max(0, min(500, max_channels)),
        "theme_mode": theme_mode,
    }


def base_channel_ids(store=None):
    return [ch["id"] for ch in sorted(channel_catalog(store)["channels"], key=lambda x: x["order"])]


def _europe_logo_key(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"\.[a-z]{2,3}$", "", value)
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def _europe_logo_source(channel, theme):
    aliases = EUROPE_LOGO_LIBRARY.get("aliases", {})
    assets = EUROPE_LOGO_LIBRARY.get("assets", {})
    values = [
        channel.get("name"),
        channel.get("source_name"),
        channel.get("source_id"),
        *(channel.get("xmltv_ids") or []),
        *(channel.get("aliases") or []),
    ]
    country = str(channel.get("source_country") or "").lower()
    if not country:
        match = re.match(r"^([a-z]{2})[_:]", str(channel.get("id") or "").lower())
        if match:
            country = match.group(1)

    candidates = [
        assets.get(asset_id) or {}
        for key in (_europe_logo_key(value) for value in values)
        if key
        for asset_id in aliases.get(key, [])
    ]
    # Check every sender identity in its country before accepting a foreign
    # namesake. Preserve international fallback only when no local match exists.
    if country:
        for item in candidates:
            if country in (item.get("countries") or []) and item.get(theme):
                return item[theme]
    for item in candidates:
        if item.get(theme):
            return item[theme]
    return ""


def _logo_source_for_channel(channel, theme):
    bundled = LOGO_LIBRARY["channels"].get(str(channel.get("source_channel_id") or channel.get("id") or ""))
    if bundled and bundled.get(theme):
        return bundled[theme]
    europe = _europe_logo_source(channel, theme)
    if europe:
        return europe
    if theme == "light":
        candidates = [
            channel.get("logo_file_light"),
            channel.get("logo_file"),
            channel.get("logo_light"),
        ]
    else:
        candidates = [
            channel.get("logo_file"),
            channel.get("logo_file_light"),
            channel.get("logo_dark"),
        ]
    # Resolve indexed library artwork, including verified background updates.
    # Do not fetch individual feed/broadcaster URLs for unmatched stations;
    # the native runtime supplies their local text fallback.
    return next(
        (
            str(value).strip()
            for value in candidates
            if value and not str(value).startswith(("http://", "https://"))
        ),
        "",
    )


def _normalized_text_logo_svg(name, theme):
    label = html.escape(str(name or "TV"))
    length = len(str(name or "TV"))
    font_size = 30 if length <= 10 else 24 if length <= 18 else 19
    fill = "#f4f6f8" if theme == "dark" else "#20242a"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="260" height="64" viewBox="0 0 260 64">
  <text x="130" y="39" text-anchor="middle"
        font-family="Arial,Helvetica,sans-serif" font-size="{font_size}"
        font-weight="700" fill="{fill}">{label}</text>
</svg>
"""


def known_channel_ids(store=None):
    store = active_store(store)
    ids = set(base_channel_ids(store))
    if store is not None:
        ids.update(ch.get("id") for ch in getattr(store, "channels", []) if ch.get("id"))
    return ids

def merge_channel_order(saved_order, store=None):
    default_order = base_channel_ids(store)
    known = known_channel_ids(store)
    order = []

    for channel_id in saved_order if isinstance(saved_order, list) else []:
        if isinstance(channel_id, str) and channel_id in known and channel_id not in order:
            order.append(channel_id)

    # Keep the curated main channels as the default preset. Newly discovered
    # feed channels stay available in the catalogue but are not enabled
    # automatically.
    for channel_id in default_order:
        if channel_id in order:
            continue
        base_index = default_order.index(channel_id)
        following = next((x for x in default_order[base_index + 1:] if x in order), None)
        if following:
            order.insert(order.index(following), channel_id)
            continue
        preceding = next((x for x in reversed(default_order[:base_index]) if x in order), None)
        if preceding:
            order.insert(order.index(preceding) + 1, channel_id)
        else:
            order.append(channel_id)

    return order

def load_channel_preferences(store=None):
    raw = read_json_file(channel_preferences_file(store), {})

    order = merge_channel_order(raw.get("order"), store)
    known = known_channel_ids(store)
    saved_hidden = raw.get("hidden")
    hidden = [x for x in saved_hidden if isinstance(x, str) and x in known] if isinstance(saved_hidden, list) else []
    return {"order": order, "hidden": hidden}

def save_channel_preferences(order, hidden, store=None):
    known = known_channel_ids(store)
    clean_order = []
    for channel_id in order or []:
        if channel_id in known and channel_id not in clean_order:
            clean_order.append(channel_id)

    prefs = {
        "order": clean_order,
        "hidden": [x for x in hidden if x in known],
    }
    write_json_file(channel_preferences_file(store), prefs)
    return prefs

def reset_channel_preferences(store=None):
    try:
        channel_preferences_file(store).unlink()
    except FileNotFoundError:
        pass
    return {"order": base_channel_ids(store), "hidden": []}


def wake_sensors():
    GUIDE_WAKE()


class EPGStore(GuideStore):
    """Store bound to the shared application services."""

    runtime = sys.modules[__name__]
STORE = EPGStore()
COUNTRY_STORES = {STORE.country: STORE}
REQUIRED_COUNTRIES = frozenset({STORE.country})
SETTINGS_LOCK = threading.Lock()
PERSONAL_CHANNELS = PersonalChannels(sys.modules[__name__])


def prune_country_stores(keep=()):
    """Called under SETTINGS_LOCK; retain used countries and in-flight refreshes."""
    global REQUIRED_COUNTRIES
    selected = PERSONAL_CHANNELS.load(STORE)["order"]
    required = {STORE.country}
    required.update(key.partition(":")[0] for key in selected)
    REQUIRED_COUNTRIES = frozenset(required)
    required.update(keep)  # A reader may retain an old cache without restarting its IO.
    for country, store in list(COUNTRY_STORES.items()):
        if country not in required and not store.refresh_running:
            del COUNTRY_STORES[country]

class Handler(GuideRequestHandler):
    """Operation dispatcher bound to the shared application services."""

    runtime = sys.modules[__name__]
