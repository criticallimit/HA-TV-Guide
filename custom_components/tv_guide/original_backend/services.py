"""Entry-owned programme engine, metadata and persistence adapters."""
import html
import re
import threading
from datetime import datetime
from urllib.request import urlopen
from .api import GuideOperations
from .json_files import read_json_file, write_json_file
from .personal_channels import PersonalChannels
from .programme_values import EPG_TIMEZONE as EPG_TIMEZONE
from .programme_values import feed_channel_id as feed_channel_id
from .programme_values import first_text as first_text
from .programme_values import normalize as normalize
from .programme_values import xmltv_datetime as xmltv_datetime
from .providers import ARD_PROGRAM_URL as ARD_PROGRAM_URL
from .providers import ARD_RB_PROGRAM_URL as ARD_RB_PROGRAM_URL
from .providers import SR_PROGRAM_URL as SR_PROGRAM_URL
from .providers import SWR_PROGRAM_URL as SWR_PROGRAM_URL
from .providers import ZDF_PROGRAM_URL as ZDF_PROGRAM_URL
from .store import GuideStore
from ..languages import LANGUAGES
from .bundled_metadata import load_logo_metadata
from .cache_catalogue import CACHE_SCHEMA_VERSION

class ProgrammeEngine:

    def __init__(self, storage, countries, catalogs, locale, settings, wake):
        self.ARD_PROGRAM_URL = ARD_PROGRAM_URL
        self.ARD_RB_PROGRAM_URL = ARD_RB_PROGRAM_URL
        self.EPG_TIMEZONE = EPG_TIMEZONE
        self.SR_PROGRAM_URL = SR_PROGRAM_URL
        self.SWR_PROGRAM_URL = SWR_PROGRAM_URL
        self.ZDF_PROGRAM_URL = ZDF_PROGRAM_URL
        self.datetime = datetime
        self.feed_channel_id = feed_channel_id
        self.first_text = first_text
        self.normalize = normalize
        self.urlopen = urlopen
        self.xmltv_datetime = xmltv_datetime
        self.settings = settings
        self.locale = locale
        self.wake = wake
        self.COUNTRIES = countries
        self.COUNTRY_CATALOGS = catalogs
        self.LOGO_LIBRARY, self.EUROPE_LOGO_LIBRARY = load_logo_metadata()
        self.OPTIONS_FILE = storage / 'options.json'
        self.CACHE_FILE = storage / 'tv_guide_epg.xml.gz'
        self.PARSED_CACHE_FILE = storage / 'tv_guide_epg_parsed.json'
        self.PARSED_CACHE_SCHEMA_VERSION = CACHE_SCHEMA_VERSION
        self.CHANNEL_PREFS_FILE = storage / 'tv_guide_channel_order.json'
        self.DEFAULT_REFRESH_MINUTES = 180
        self.LANGUAGES = set(LANGUAGES)
        owner = self

        class EPGStore(GuideStore):
            runtime = owner
        self.EPGStore = EPGStore
        self.STORE = self.EPGStore()
        self.COUNTRY_STORES = {self.STORE.country: self.STORE}
        self.REQUIRED_COUNTRIES = frozenset({self.STORE.country})
        self.SETTINGS_LOCK = threading.Lock()
        self.PERSONAL_CHANNELS = PersonalChannels(self)
        self.operations = GuideOperations(self)

    def home_assistant_locale(self):
        return dict(self.locale)

    def save_options_file(self, options):
        self.settings.replace(options, self.OPTIONS_FILE)

    def country_code(self, value):
        value = str(value or 'de').lower()
        return value if value in self.COUNTRIES else 'de'

    def country_file(self, path, country):
        prefix = self.COUNTRIES[country].get('storage_prefix', country + '_')
        return path.with_name(prefix + path.name)

    def active_store(self, store=None):
        return store if store is not None else getattr(self, 'STORE', None)

    def channel_catalog(self, store=None):
        store = self.active_store(store)
        return store.catalog if store is not None else self.COUNTRY_CATALOGS[self.country_code(None)]

    def channel_preferences_file(self, store=None):
        store = self.active_store(store)
        return self.country_file(self.CHANNEL_PREFS_FILE, getattr(store, 'country', 'de'))

    def load_options(self):
        data = self.settings.read(self.OPTIONS_FILE)
        try:
            refresh = int(data.get('refresh_minutes') or self.DEFAULT_REFRESH_MINUTES)
        except Exception:
            refresh = self.DEFAULT_REFRESH_MINUTES
        notification_service = str(data.get('notification_service') or 'persistent_notification.create').strip().lower()
        if not re.match('^[a-z0-9_]+\\.[a-z0-9_]+$', notification_service):
            notification_service = 'persistent_notification.create'
        language = data.get('language')
        return {'country': self.country_code(data.get('country')), 'language': language if isinstance(language, str) and language in self.LANGUAGES | {'auto'} else 'auto', 'refresh_minutes': max(30, min(1440, refresh)), 'notification_service': notification_service}

    def load_options_ui(self):
        data = self.settings.read(self.OPTIONS_FILE)
        default_view = str(data.get('default_view') or 'now')
        if default_view not in {'now', '1800', '2015', '2200'}:
            default_view = 'now'
        try:
            columns = int(data.get('columns_desktop') or 5)
        except Exception:
            columns = 5
        try:
            max_channels = int(data.get('max_channels') or 0)
        except Exception:
            max_channels = 0
        theme_mode = str(data.get('theme_mode') or 'auto').lower()
        if theme_mode not in {'auto', 'dark', 'light'}:
            theme_mode = 'auto'
        return {'country_language': self.COUNTRIES[self.country_code(data.get('country'))].get('language'), 'default_view': default_view, 'columns_desktop': max(3, min(6, columns)), 'max_channels': max(0, min(500, max_channels)), 'theme_mode': theme_mode}

    def base_channel_ids(self, store=None):
        return [ch['id'] for ch in sorted(self.channel_catalog(store)['channels'], key=lambda x: x['order'])]

    def _europe_logo_key(self, value):
        value = str(value or '').strip().lower()
        value = re.sub('\\.[a-z]{2,3}$', '', value)
        value = value.replace('&', 'and')
        value = re.sub('[^a-z0-9]+', '-', value).strip('-')
        return value

    def _europe_logo_source(self, channel, theme):
        aliases = self.EUROPE_LOGO_LIBRARY.get('aliases', {})
        assets = self.EUROPE_LOGO_LIBRARY.get('assets', {})
        values = [channel.get('name'), channel.get('source_name'), channel.get('source_id'), *(channel.get('xmltv_ids') or []), *(channel.get('aliases') or [])]
        country = str(channel.get('source_country') or '').lower()
        if not country:
            match = re.match('^([a-z]{2})[_:]', str(channel.get('id') or '').lower())
            if match:
                country = match.group(1)
        candidates = [assets.get(asset_id) or {} for key in (self._europe_logo_key(value) for value in values) if key for asset_id in aliases.get(key, [])]
        if country:
            for item in candidates:
                if country in (item.get('countries') or []) and item.get(theme):
                    return item[theme]
        for item in candidates:
            if item.get(theme):
                return item[theme]
        return ''

    def _logo_source_for_channel(self, channel, theme):
        bundled = self.LOGO_LIBRARY['channels'].get(str(channel.get('source_channel_id') or channel.get('id') or ''))
        if bundled and bundled.get(theme):
            return bundled[theme]
        europe = self._europe_logo_source(channel, theme)
        if europe:
            return europe
        if theme == 'light':
            candidates = [channel.get('logo_file_light'), channel.get('logo_file'), channel.get('logo_light')]
        else:
            candidates = [channel.get('logo_file'), channel.get('logo_file_light'), channel.get('logo_dark')]
        return next((str(value).strip() for value in candidates if value and (not str(value).startswith(('http://', 'https://')))), '')

    def _normalized_text_logo_svg(self, name, theme):
        label = html.escape(str(name or 'TV'))
        length = len(str(name or 'TV'))
        font_size = 30 if length <= 10 else 24 if length <= 18 else 19
        fill = '#f4f6f8' if theme == 'dark' else '#20242a'
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="260" height="64" viewBox="0 0 260 64">\n  <text x="130" y="39" text-anchor="middle"\n        font-family="Arial,Helvetica,sans-serif" font-size="{font_size}"\n        font-weight="700" fill="{fill}">{label}</text>\n</svg>\n'

    def known_channel_ids(self, store=None):
        store = self.active_store(store)
        ids = set(self.base_channel_ids(store))
        if store is not None:
            ids.update((ch.get('id') for ch in getattr(store, 'channels', []) if ch.get('id')))
        return ids

    def merge_channel_order(self, saved_order, store=None):
        default_order = self.base_channel_ids(store)
        known = self.known_channel_ids(store)
        order = []
        for channel_id in saved_order if isinstance(saved_order, list) else []:
            if isinstance(channel_id, str) and channel_id in known and (channel_id not in order):
                order.append(channel_id)
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

    def load_channel_preferences(self, store=None):
        raw = read_json_file(self.channel_preferences_file(store), {})
        order = self.merge_channel_order(raw.get('order'), store)
        known = self.known_channel_ids(store)
        saved_hidden = raw.get('hidden')
        hidden = [x for x in saved_hidden if isinstance(x, str) and x in known] if isinstance(saved_hidden, list) else []
        return {'order': order, 'hidden': hidden}

    def save_channel_preferences(self, order, hidden, store=None):
        known = self.known_channel_ids(store)
        clean_order = []
        for channel_id in order or []:
            if channel_id in known and channel_id not in clean_order:
                clean_order.append(channel_id)
        prefs = {'order': clean_order, 'hidden': [x for x in hidden if x in known]}
        write_json_file(self.channel_preferences_file(store), prefs)
        return prefs

    def reset_channel_preferences(self, store=None):
        try:
            self.channel_preferences_file(store).unlink()
        except FileNotFoundError:
            pass
        return {'order': self.base_channel_ids(store), 'hidden': []}

    def wake_sensors(self, *, programmes=True, routing=False):
        self.wake(programmes=programmes, routing=routing)

    def prune_country_stores(self, keep=()):
        """Called under SETTINGS_LOCK; retain used countries and in-flight refreshes."""
        selected = self.PERSONAL_CHANNELS.load(self.STORE)['order']
        required = {self.STORE.country}
        required.update((key.partition(':')[0] for key in selected))
        self.REQUIRED_COUNTRIES = frozenset(required)
        required.update(keep)
        for country, store in list(self.COUNTRY_STORES.items()):
            if country not in required and (not store.refresh_running):
                del self.COUNTRY_STORES[country]
