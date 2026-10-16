"""Host the reference programme engine without its server or Supervisor workers."""
from datetime import datetime, timezone
from hashlib import sha256
from functools import partial
import json
import logging
from pathlib import Path
from time import monotonic, perf_counter
import threading
from uuid import uuid4
from urllib.parse import quote
from .logo_assets import bundled_logo_library
from .logo_download import LogoDownload
from .logo_updates import LogoUpdates
from .worker_io import worker_urlopen
from .ui_payload import guide_preview
from .countries import COUNTRIES, ROOT as COUNTRY_ROOT
from .provider_transport import ProviderTransport
from .work_scheduler import WorkScheduler
from .settings_state import SettingsState
from .storage_cleanup import remove_legacy_storage
from .programme_repository import ProgrammeRepository, compact_guide
from .original_backend.services import ProgrammeEngine

GET_ENDPOINTS = {"guide", "channels", "personal-channels", "channel-settings", "settings", "status"}
POST_ENDPOINTS = {"settings", "personal-channels", "channel-settings"}
_LOGGER = logging.getLogger(__name__)


class GuideRuntime:
    """Entry-owned reference runtime, cache directory and stoppable worker pool."""

    def __init__(self, storage: Path, options: dict, locale: dict, wake, persist_settings=True, provider_client=None):
        storage.mkdir(parents=True, exist_ok=True)
        self._preparation_marker = storage / 'preparation-complete.json'
        self._first_install = not self._preparation_marker.exists()
        self._installation_id = storage.name
        self.closed = False
        self._logos = bundled_logo_library()
        self._logos.configure_cache(storage / 'logos')
        self.logo_updates = LogoUpdates(self._logos, storage / 'logos')
        self.logo_download = LogoDownload(self._logos)
        self._lock = threading.RLock()
        self._request_lock = threading.RLock()
        self._settings_request_lock = threading.RLock()
        self._personal_request_lock = threading.RLock()
        self._snapshot_lock = threading.Lock()
        self._jobs = {}
        self._worker_context = threading.local()
        self._wake = wake
        self._guide_cache = None
        self._guide_cached_at = 0.0
        self._guide_revision = uuid4().hex
        self._guide_generation = 0
        self._settings_generation = 0
        self._snapshot_cache = None
        self.programmes = ProgrammeRepository()
        self.provider_client = provider_client
        self.settings = SettingsState(storage / "options.json", {**options, "country":options.get("country") or "de"}, persistent=persist_settings)
        catalogs = {code:json.loads((COUNTRY_ROOT / "catalogs" / item["catalog"]).read_text(encoding="utf-8"))
                    for code,item in COUNTRIES.items()}
        runtime = ProgrammeEngine(storage, COUNTRIES, catalogs, locale, self.settings, self._backend_changed)
        self.runtime = runtime
        remove_legacy_storage(storage, native_settings=not persist_settings)
        self._pool = WorkScheduler(2)
        try:
            self._cache_pool = WorkScheduler(1, "tv-guide-cache")
        except BaseException:
            self._pool.shutdown(cancel_futures=True)
            raise
        if provider_client is not None:
            provider_client.stopped = self._worker_stopped
        self.transport = ProviderTransport(provider_client.open if provider_client is not None else runtime.urlopen)
        runtime.urlopen = partial(worker_urlopen, self.transport.open, self._worker_stopped)
        runtime.start_background = self.start_background
        runtime.worker_stopped = self._worker_stopped
        runtime.normalized_logo_urls = self.logo_urls
        runtime.public_programmes = self.programmes.programmes
        runtime.restore_country = self.restore_country

    def _invalidate_caches(self, *, programmes=True):
        with self._lock:
            self._guide_cache = None
            self._guide_generation += 1
            if programmes:
                self._snapshot_cache = None
                self.programmes.clear()

    def _backend_changed(self, *, programmes=True, routing=False):
        # Called by provider workers when new programme data become available.
        self._invalidate_caches(programmes=programmes)
        if routing:
            with self._lock:
                self._snapshot_cache = None
        self._wake()

    def logo_urls(self, channel):
        """Use TV Guide main logos and the complete offline station library."""
        raw_id = str(channel.get("id") or "")
        prefix = raw_id.split(':',1)[0].split('_',1)[0]
        country = channel.get('source_country') or (prefix if prefix in self.runtime.COUNTRIES else self.runtime.STORE.country)
        channel_id = str(channel.get("source_channel_id") or raw_id).split(":")[-1]
        curated = self._logos.channel_urls(country, channel_id)
        if curated:
            return curated['logo_normalized_light'], curated['logo_normalized_dark']
        original = {**channel, 'source_country': country}
        result = []
        for theme in ('light', 'dark'):
            source = self.runtime._logo_source_for_channel(original, theme)
            if self._logos.contains(source):
                bundled = self.runtime.LOGO_LIBRARY['channels'].get(channel_id)
                normalized = bool(bundled and source == bundled.get(theme)) or source.startswith(('logos/europe/', 'logos/uk/'))
                result.append('/tv_guide/logo/' + quote(source, safe='/') + '?v=' + self._logos.revision + ('' if normalized else '&normalize=1'))
            else:
                svg = self.runtime._normalized_text_logo_svg(channel.get('name') or channel_id, theme)
                result.append('data:image/svg+xml,' + quote(svg))
        return tuple(result)

    def _worker_stopped(self):
        """Stop obsolete country IO without interrupting personal-list countries."""
        store = getattr(self._worker_context, 'store', None)
        if store is not None and (store.country not in self.runtime.REQUIRED_COUNTRIES
                                  or self.runtime.COUNTRY_STORES.get(store.country) is not store):
            self._worker_context.cancelled = True
        return self.closed or getattr(self._worker_context, 'cancelled', False)

    def start_background(self, function, **kwargs):
        with self._lock:
            if self.closed:
                return
            # Bound methods identify a particular country store. Keep at most
            # one queued/running refresh per store, including forced requests.
            if function in self._jobs:
                job = self._jobs[function]
                if kwargs.get('force') and not job['forced']:
                    job['pending_force'] = True
                return job['future']
            job = {'kwargs': dict(kwargs), 'forced': bool(kwargs.get('force')), 'pending_force': False}
            self._jobs[function] = job
            def run():
                while True:
                    owner = getattr(function, '__self__', None)
                    store = owner if isinstance(owner, self.runtime.EPGStore) else None
                    self._worker_context.store = store
                    self._worker_context.cancelled = False
                    cancelled = False
                    try:
                        if self._worker_stopped():
                            if store is not None:
                                with self.runtime.SETTINGS_LOCK:
                                    store.refresh_running = False
                                    self.runtime.prune_country_stores()
                        else:
                            function(**job['kwargs'])
                        cancelled = self._worker_context.cancelled
                    finally:
                        self._worker_context.store = None
                        self._worker_context.cancelled = False
                    with self._lock:
                        retry_selected = (cancelled and store is not None and store.country in self.runtime.REQUIRED_COUNTRIES
                                          and self.runtime.COUNTRY_STORES.get(store.country) is store)
                        if not self.closed and (job['pending_force'] or retry_selected):
                            job['pending_force'] = False
                            job['forced'] = True
                            job['kwargs']['force'] = True
                        else:
                            if self._jobs.get(function) is job:
                                self._jobs.pop(function)
                            return
            owner = getattr(function, '__self__', None)
            def priority():
                if owner is self.runtime.STORE:
                    return 0
                return 20 if function == self._download_logos else 10
            future = self._pool.submit(run, priority=priority)
            job['future'] = future
            def finished(completed):
                with self._lock:
                    if self._jobs.get(function) is job:
                        self._jobs.pop(function)
                if not completed.cancelled():
                    try:
                        completed.result()
                    except Exception:
                        _LOGGER.exception("TV Guide provider worker failed")
                # Logo verification/downloads do not change programme data.
                # Keep guide revisions and the large HA snapshot reusable.
                if function != self._download_logos:
                    self._backend_changed()
            future.add_done_callback(finished)
            return future

    def restore_country(self, store):
        def restore():
            try:
                if self.closed or self.runtime.COUNTRY_STORES.get(store.country) is not store or store.country not in self.runtime.REQUIRED_COUNTRIES:
                    return
                with store.lock:
                    if store._cache_pending:
                        store._load_parsed_cache()
                        store._cache_pending = False
            finally:
                store._cache_loading = False
                store.refresh_running = False
            if not self.closed:
                if store.country in self.runtime.REQUIRED_COUNTRIES:
                    store.ensure_fresh_async()
                self._backend_changed()
        with self._lock:
            if self.closed:
                return
            if getattr(store, '_cache_loading', False):
                return store._cache_future
            store._cache_loading = True
            store.refresh_running = True
            store._cache_future = self._cache_pool.submit(restore, priority=lambda:0 if store is self.runtime.STORE else 10)
            return store._cache_future

    def maintain_caches(self):
        """Check used caches independently of coordinator notification scheduling."""
        with self._lock:
            if self.closed:
                return
        with self.runtime.SETTINGS_LOCK:
            self.runtime.prune_country_stores()
            active = self.runtime.STORE
            stores = [active, *(store for store in self.runtime.COUNTRY_STORES.values() if store is not active)]
        for store in stores:
            store.ensure_fresh_async()
        self.start_logo_download()

    def start_logo_download(self, force=False):
        if not self.closed:
            return self.start_background(self._download_logos, force=force)

    def _download_logos(self, force=False):
        self.logo_download.run(lambda: self.closed, verify=force)
        if not self.closed and self.logo_download.status()['ready']:
            replacement = self.logo_updates.check(lambda: self.closed, force=force)
            if replacement is not None:
                self.logo_download = replacement
                # New image URLs reach open cards through their regular guide
                # refresh. Programme records and coordinator entities are unchanged.
                self._invalidate_caches(programmes=False)

    def preparation_status(self):
        with self._lock:
            store = self.runtime.STORE
            programmes = {'running': store.refresh_running,
                          'ready': any(ch.get('programs') for ch in store.channels),
                          'sources_completed': len(store.source_metrics),
                          'error': bool(store.last_error) and not store.refresh_running}
            logos = self.logo_download.status()
            job = self._jobs.get(self._download_logos)
            if job is not None and (not logos['ready'] or job.get('forced')):
                logos = {**logos, 'running': True, 'ready': False}
            complete = logos['ready'] and programmes['ready'] and not programmes['running'] and not programmes['error']
            first_install = self._first_install
            if complete and self._first_install:
                temporary = self._preparation_marker.with_suffix('.tmp')
                try:
                    temporary.write_text('{}', encoding='utf-8')
                    temporary.replace(self._preparation_marker)
                    self._first_install = False
                except OSError:
                    _LOGGER.warning('TV Guide could not persist preparation completion', exc_info=True)
            return {'installation_id': self._installation_id, 'first_install': first_install,
                    'complete': complete, 'logos': logos, 'programmes': programmes}

    def refresh_active(self):
        """Use the same owned pool for periodic coordinator refreshes."""
        future = self.start_background(self.runtime.STORE.refresh)
        if future is not None:
            future.result()


    def request(self, endpoint: str, method: str, body=None):
        """Never return a guide built across a committed settings change."""
        if endpoint != "guide" or method != "GET":
            return self._request(endpoint, method, body)
        with self._request_lock:
            while True:
                with self._lock:
                    generation = self._settings_generation
                result = self._request(endpoint, method, body)
                with self._lock:
                    if generation == self._settings_generation or self.closed:
                        return result

    def _request(self, endpoint: str, method: str, body=None):
        """Dispatch the original route code in-process, without opening HTTP ports."""
        if method == "GET" and endpoint == "refresh":
            with self._lock:
                if self.closed:
                    raise RuntimeError("TV Guide is unloading")
                self.start_background(self.runtime.STORE.refresh, force=True)
                return {"ok": True, "refresh_started": True}
        if endpoint not in (GET_ENDPOINTS if method == "GET" else POST_ENDPOINTS if method == "POST" else set()):
            raise ValueError("Unsupported reference operation")
        encoded = json.dumps(body or {}).encode("utf-8")
        if len(encoded) > 65536:
            raise ValueError("Request is too large")
        # Large guide rendering must not monopolize settings reads/writes or
        # worker notifications. Only cache bookkeeping uses the shared lock.
        request_lock = (self._settings_request_lock if endpoint == "settings"
                        else self._personal_request_lock if endpoint == "personal-channels"
                        else self._request_lock)
        with request_lock:
            preview = method == "GET" and endpoint == "guide" and isinstance(body, dict) and body.get("preview") is True
            with self._lock:
                if self.closed:
                    raise RuntimeError("TV Guide is unloading")
                if method == "GET" and endpoint == "guide" and not preview and isinstance(body, dict) and body.get("known_revision") == f"{self._guide_revision}:{self._guide_generation}":
                    return {"unchanged": True, "revision": f"{self._guide_revision}:{self._guide_generation}"}
                cached = self._guide_cache if monotonic() - self._guide_cached_at < 10 else None
                if method == "POST":
                    self._invalidate_caches(programmes=False)
                generation = self._guide_generation
            if method == "GET" and endpoint == "guide" and cached is not None:
                return self._guide_response(cached, body, preview)
            started = perf_counter()
            previous_country = self.runtime.STORE.country
            if method == "GET":
                result = self.runtime.operations.get(endpoint)
            else:
                try:
                    result = self.runtime.operations.post(endpoint, body or {})
                finally:
                    with self._lock:
                        if endpoint == "settings":
                            self._settings_generation += 1
                        self._invalidate_caches(programmes=False)
                        if previous_country != self.runtime.STORE.country:
                            self._snapshot_cache = None
            if endpoint == "guide":
                result["revision"] = f"{self._guide_revision}:{generation}"
                with self._lock:
                    if generation == self._guide_generation and not self.closed:
                        self._guide_cache = result
                        self._guide_cached_at = monotonic()
                _LOGGER.debug("TV Guide prepared guide in %.1f ms", (perf_counter() - started) * 1000)
            return self._guide_response(result, body, preview)

    @staticmethod
    def _guide_response(payload, body, preview):
        result = guide_preview(payload, body) if preview else payload
        return compact_guide(result) if isinstance(body, dict) and body.get("compact") is True else result

    def snapshot(self, store=None):
        store = store if store is not None else self.runtime.STORE
        channels = list(store.channels)
        records = [{"channel": channel["id"], "start": item["start"], "stop": item["end"],
                    "title": item["title"], "description": item.get("desc", ""),
                    "subtitle": item.get("subtitle", ""), "category": item.get("category", "")}
                   for channel in channels for item in channel.get("programs", [])]
        catalogue = [{"id": channel["id"], "name": channel["name"], "available": bool(channel.get("programs")),
                      "xmltv_id": channel["id"]} for channel in channels if channel.get("preset")]
        return records, catalogue, [{"id": ch["id"], "name": ch["name"]} for ch in channels]

    def state_snapshot(self):
        """Capture metadata quickly; build large EPG snapshots outside shared locks."""
        with self._snapshot_lock:
            while True:
                with self.runtime.SETTINGS_LOCK:
                    store = self.runtime.STORE
                    status = {
                        'country': store.country,
                        'refresh_running': store.refresh_running,
                        'source_attempts': list(store.source_metrics),
                        'last_loaded': store.last_loaded,
                        'refresh_minutes': store.options.get('refresh_minutes', 180),
                    }
                    with self._lock:
                        generation = self._guide_generation
                        cached = self._snapshot_cache
                snapshot = cached if cached is not None else self.snapshot(store)
                with self._lock:
                    if generation != self._guide_generation and not self.closed:
                        continue
                    if not self.closed:
                        self._snapshot_cache = snapshot
                return (*snapshot, status)

    def close(self):
        with self._lock:
            self.closed = True
        if self.provider_client is not None:
            self.provider_client.close()
        # Retain ownership of active requests after marking the runtime closed.
        with self._request_lock, self._settings_request_lock, self._personal_request_lock, self._snapshot_lock:
            pass
        self._cache_pool.shutdown(wait=True, cancel_futures=True)
        self._pool.shutdown(wait=True, cancel_futures=True)
