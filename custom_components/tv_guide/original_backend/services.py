import base64
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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
WWW = GUIDE_ASSET_ROOT / "www"
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
LOGO_CACHE_DIR = GUIDE_STORAGE_ROOT / "tv_guide_logos"
LOGO_RENDER_VERSION = 5


# Every curated main channel goes through the same official-source layer. Channels
# without a stable public schedule endpoint remain XMLTV-only until a verified
# official endpoint is added here; no guessed URLs are used.
OFFICIAL_PROVIDER_AUDIT = {
    channel_id: OFFICIAL_PROVIDER_BY_CHANNEL.get(channel_id)
    for channel_id in [ch["id"] for ch in CHANNELS["channels"]]
}


DEFAULT_REFRESH_MINUTES = 180
BACKGROUND_PRELOAD_DELAY_SECONDS = 120
BACKGROUND_PRELOAD_POLL_SECONDS = 2

LANGUAGES = {"da", "de", "en", "nl", "fr", "it", "nb", "sv"}
TRANSLATIONS = {
    code: json.loads((WWW / "locales" / f"{code}.json").read_text(encoding="utf-8"))
    for code in LANGUAGES
}


def language_code(value):
    value = str(value or "").lower().replace("_", "-").split("-")[0]
    return "nb" if value == "no" else value if value in LANGUAGES else "en"




def home_assistant_locale(wait=True):
    return dict(GUIDE_LOCALE)


def effective_language(value=None):
    options = load_options()
    configured = value or options.get("language", "auto")
    if configured != "auto":
        return language_code(configured)
    locale = home_assistant_locale()
    if locale.get("language"):
        return language_code(locale["language"])
    country = str(locale.get("country") or options.get("country") or "de").lower()
    return {"de": "de", "at": "de", "nl": "nl", "no": "nb", "fr": "fr", "dk": "da", "se": "sv", "gb": "en"}.get(country, "en")


def translate(message, language, **values):
    catalogue = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    message = catalogue.get(message, TRANSLATIONS["en"].get(message, message))
    return re.sub(r"\{(\w+)\}", lambda match: str(values.get(match[1], match[0])), message)


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
    return {
        "country": country_code(data.get("country")),
        "language": data.get("language") if data.get("language") in LANGUAGES | {"auto"} else "auto",
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
    # Runtime logo downloads are intentionally disabled. The shipped country
    # library and Europe pack are authoritative; unmatched stations use the
    # generated local text fallback instead of fetching a feed/broadcaster URL.
    return next(
        (
            str(value).strip()
            for value in candidates
            if value and not str(value).startswith(("http://", "https://"))
        ),
        "",
    )


def _logo_mime(source, content_type, data):
    value = (content_type or "").split(";", 1)[0].strip().lower()
    if value in {"image/svg+xml", "image/png", "image/jpeg", "image/webp", "image/gif"}:
        return value
    lower = str(source or "").lower()
    if lower.endswith(".svg") or data.lstrip().startswith(b"<svg"):
        return "image/svg+xml"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None


def _read_logo_source(source):
    if not source:
        return None
    if source.startswith(("http://", "https://")):
        req = Request(
            source,
            headers={
                "User-Agent": "Mozilla/5.0 HomeAssistant-TV-Guide/1.0",
                "Accept": "image/avif,image/webp,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        with urlopen(req, timeout=10) as response:
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                return None
            mime = _logo_mime(source, response.headers.get("Content-Type"), data)
            return (data, mime) if mime else None

    path = (WWW / source.lstrip("/")).resolve()
    if WWW.resolve() not in path.parents:
        return None
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        return None
    data = path.read_bytes()
    mime = _logo_mime(source, None, data)
    return (data, mime) if mime else None


def _normalized_logo_svg(data, mime, theme):
    encoded = base64.b64encode(data).decode("ascii")
    image_href = f"data:{mime};base64,{encoded}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="260" height="64" viewBox="0 0 260 64">
  <image x="5" y="4" width="250" height="56" preserveAspectRatio="xMidYMid meet"
         href="{image_href}"/>
</svg>
"""


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


def normalized_logo_path(channel, theme):
    theme = "dark" if theme == "dark" else "light"
    source = _logo_source_for_channel(channel, theme)
    bundled = LOGO_LIBRARY["channels"].get(str(channel.get("source_channel_id") or channel.get("id") or ""))
    if bundled and source == bundled.get(theme):
        path = (WWW / source).resolve()
        if WWW.resolve() in path.parents and path.is_file():
            # Library assets already have the final canvas and theme treatment.
            return path
    if source.startswith(("logos/europe/", "logos/uk/")):
        path = (WWW / source).resolve()
        if WWW.resolve() in path.parents and path.is_file():
            # Shipped Europe-pack and UK fallback assets already use the final
            # 260x64 canvas and require no runtime cache or network access.
            return path
    source_identity = _logo_source_identity(source) if source else f"text:{channel.get('name') or channel.get('id') or 'TV'}"
    source_key_value = f"{LOGO_RENDER_VERSION}:{source_identity}"
    source_key = hashlib.sha1(source_key_value.encode("utf-8")).hexdigest()[:12]
    channel_key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(channel.get("id") or "channel"))
    LOGO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = LOGO_CACHE_DIR / f"{channel_key}-{theme}-{source_key}.svg"
    if target.is_file() and target.stat().st_size > 100:
        return target

    try:
        tmp = target.with_suffix(".tmp")
        if not source:
            tmp.write_text(
                _normalized_text_logo_svg(channel.get("name"), theme),
                encoding="utf-8",
            )
            os.replace(tmp, target)
            return target

        loaded = _read_logo_source(source)
        if not loaded:
            tmp.write_text(
                _normalized_text_logo_svg(channel.get("name"), theme),
                encoding="utf-8",
            )
            os.replace(tmp, target)
            return target
        data, mime = loaded
        tmp.write_text(_normalized_logo_svg(data, mime, theme), encoding="utf-8")
        os.replace(tmp, target)
        return target
    except Exception as exc:
        print(
            f"[TV Guide] Logo konnte nicht normalisiert werden ({channel.get('name')} / {theme}): {exc}",
            flush=True,
        )
        return None


@lru_cache(maxsize=128)
def _standalone_europe_logo(path):
    # SVGs used as <img> cannot load external images, even local relative URLs.
    # Keep the shipped artwork deduplicated and embed it only in the response.
    svg = path.read_text(encoding="utf-8")

    def embed(match):
        asset = (path.parent / match[1]).resolve()
        root = (WWW / "logos/europe/assets").resolve()
        if root not in asset.parents or not asset.is_file():
            raise ValueError("Invalid Europe logo asset")
        data = asset.read_bytes()
        mime = _logo_mime(str(asset), None, data)
        return 'href="data:' + mime + ';base64,' + base64.b64encode(data).decode("ascii") + '"'

    return re.sub(r'href="(\.\./assets/[^\"]+)"', embed, svg).encode("utf-8")


def normalized_logo_data(channel, theme):
    path = normalized_logo_path(channel, theme)
    if path is None:
        return None
    if (WWW / "logos/europe").resolve() in path.parents:
        return _standalone_europe_logo(path)
    return path.read_bytes()


@lru_cache(maxsize=None)
def _logo_source_identity(source):
    # Bundled files are immutable while Home Assistant is running. Hash the
    # bytes so rebuilding artwork at the same path also invalidates logo caches.
    path = (WWW / source).resolve()
    if WWW.resolve() not in path.parents or not path.is_file():
        return source
    digest = hashlib.sha256(path.read_bytes())
    if source.startswith("logos/europe/"):
        for asset in EUROPE_LOGO_LIBRARY["assets"].values():
            if source in (asset.get("light"), asset.get("dark")):
                digest.update(asset["source_sha256"].encode("ascii"))
                break
    return f"{source}:{digest.hexdigest()}"


def normalized_logo_urls(channel):
    channel_id = str(channel.get("id") or "")
    if not channel_id:
        return (None, None)
    encoded_id = quote(channel_id, safe="")
    base = f"api/channel-logo/{encoded_id}"
    urls = []
    for theme in ("light", "dark"):
        source = _logo_source_for_channel(channel, theme)
        identity = _logo_source_identity(source) if source else f"text:{channel.get('name') or channel_id}"
        asset_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        urls.append(f"{base}/{theme}.svg?v={LOGO_RENDER_VERSION}&asset={asset_key}")
    return tuple(urls)


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

    for channel_id in saved_order or []:
        if channel_id in known and channel_id not in order:
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
    hidden = [x for x in raw.get("hidden", []) if x in known]
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
SETTINGS_LOCK = threading.Lock()
PERSONAL_CHANNELS = PersonalChannels(sys.modules[__name__])


def prune_country_stores(keep=()):
    """Called under SETTINGS_LOCK; retain used countries and in-flight refreshes."""
    selected = PERSONAL_CHANNELS.load(STORE)["order"]
    required = {STORE.country, *keep}
    required.update(key.partition(":")[0] for key in selected)
    for country, store in list(COUNTRY_STORES.items()):
        if country not in required and not store.refresh_running:
            del COUNTRY_STORES[country]

class Handler(GuideRequestHandler):
    """HTTP handler bound to the shared application services."""

    runtime = sys.modules[__name__]


def _wait_for_active_epg_idle():
    while STORE.refresh_running:
        time.sleep(BACKGROUND_PRELOAD_POLL_SECONDS)


def preload_country_caches_once(delay_seconds=BACKGROUND_PRELOAD_DELAY_SECONDS):
    """Warm stale caches for inactive countries sequentially.

    The active country always keeps priority. Inactive countries are checked
    one at a time, with a pause before each check, and are refreshed only when
    their existing cache is not fresh.
    """
    _wait_for_active_epg_idle()

    for country in COUNTRIES:
        if country == STORE.country:
            continue

        time.sleep(delay_seconds)
        _wait_for_active_epg_idle()

        # The user may have switched countries while the worker was waiting.
        if country == STORE.country:
            continue

        with SETTINGS_LOCK:
            store = COUNTRY_STORES.get(country)
            if store is None:
                store = EPGStore(country)
                COUNTRY_STORES[country] = store

            # Reserve the store before releasing SETTINGS_LOCK so a country
            # switch cannot start a second refresh or evict this instance.
            refresh_needed = country != STORE.country and not store.refresh_running and not store._cache_fresh()
            if refresh_needed:
                store.refresh_running = True

        try:
            if refresh_needed:
                print(
                    f"[TV Guide] Hintergrund-Vorladen startet für {COUNTRIES[country]['name']}",
                    flush=True,
                )
                store.refresh(force=False)
        finally:
            with SETTINGS_LOCK:
                prune_country_stores()
            del store




