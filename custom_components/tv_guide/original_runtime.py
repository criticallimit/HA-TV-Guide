"""Host the reference programme engine without its server or Supervisor workers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from functools import partial
import importlib.util
from io import BytesIO
import json
import logging
from pathlib import Path
from time import monotonic, perf_counter
import sys
import threading
from uuid import uuid4
from urllib.parse import quote
import zipfile
from .logo_assets import bundled_logo_library
from .worker_io import worker_urlopen

GET_ENDPOINTS = {"guide", "channels", "personal-channels", "channel-settings", "settings", "status"}
POST_ENDPOINTS = {"settings", "personal-channels", "channel-settings"}
_LOGGER = logging.getLogger(__name__)


class OriginalRuntime:
    """Entry-owned reference runtime, cache directory and stoppable worker pool."""

    def __init__(self, storage: Path, options: dict, locale: dict, wake):
        storage.mkdir(parents=True, exist_ok=True)
        assets = storage / "reference"
        with zipfile.ZipFile(Path(__file__).parent / "original_backend" / "reference-data.zip") as archive:
            for name in archive.namelist():
                target = (assets / name).resolve()
                if assets.resolve() not in target.parents:
                    raise ValueError("Invalid bundled reference path")
                target.parent.mkdir(parents=True, exist_ok=True)
                data = archive.read(name)
                if not target.exists() or target.read_bytes() != data:
                    temporary = target.with_suffix(target.suffix + '.tmp')
                    temporary.write_bytes(data)
                    temporary.replace(target)
        self.closed = False
        self._logos = bundled_logo_library()
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tv-guide")
        self._jobs = {}
        self._preload_index = 0
        self._wake = wake
        self._guide_cache = None
        self._guide_cached_at = 0.0
        self._guide_revision = uuid4().hex
        self._guide_generation = 0
        self._snapshot_cache = None
        name = __package__ + ".original_backend._entry_" + storage.name.replace("-", "_")
        self._module_name = name
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "original_backend" / "services.py")
        runtime = importlib.util.module_from_spec(spec)
        runtime.GUIDE_ASSET_ROOT = assets
        runtime.GUIDE_STORAGE_ROOT = storage
        runtime.GUIDE_LOCALE = locale
        runtime.GUIDE_WAKE = self._backend_changed
        # Persist presentation settings between HA restarts; never touch /data.
        options_path = storage / "options.json"
        try:
            previous = json.loads(options_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        if not isinstance(previous, dict):
            previous = {}
        options_tmp = options_path.with_suffix(".tmp")
        options_tmp.write_text(json.dumps({**previous, **options, "country": options.get("country") or "de"}), encoding="utf-8")
        options_tmp.replace(options_path)
        sys.modules[name] = runtime
        try:
            spec.loader.exec_module(runtime)
        except BaseException:
            sys.modules.pop(name, None)
            self._pool.shutdown(wait=False, cancel_futures=True)
            raise
        self.runtime = runtime
        runtime.urlopen = partial(worker_urlopen, runtime.urlopen, lambda:self.closed)
        runtime.start_background = self.start_background
        runtime.normalized_logo_urls = self.logo_urls

    def _backend_changed(self):
        # Called by provider workers when new programme data become available.
        with self._lock:
            self._guide_cache = None
            self._guide_generation += 1
            self._snapshot_cache = None
        self._wake()

    def logo_urls(self, channel):
        """Use TV Guide main logos and the complete offline station library."""
        raw_id = str(channel.get("id") or "")
        prefix = raw_id.split(':',1)[0].split('_',1)[0]
        country = channel.get('source_country') or (prefix if prefix in self.runtime.COUNTRIES else self.runtime.STORE.country)
        channel_id = str(channel.get("source_channel_id") or raw_id).split(":")[-1]
        root = Path(__file__).parent / "frontend" / "app" / "logos"
        result = []
        for theme in ("light", "dark"):
            path = root / f"{country}-{channel_id}-{theme}.svg"
            if path.is_file():
                result.append(f"/tv_guide/frontend/app/logos/{quote(path.name)}")
            else:
                original = {**channel, 'source_country': channel.get('source_country') or country}
                source = self.runtime._logo_source_for_channel(original, theme)
                if self._logos.contains(source):
                    bundled = self.runtime.LOGO_LIBRARY['channels'].get(str(original.get('source_channel_id') or original.get('id') or ''))
                    normalized = bool(bundled and source==bundled.get(theme)) or source.startswith(('logos/europe/','logos/uk/'))
                    result.append('/tv_guide/logo/'+quote(source,safe='/')+'?v='+self._logos.revision+('' if normalized else '&normalize=1'))
                else:
                    svg = self.runtime._normalized_text_logo_svg(channel.get("name") or channel_id, theme)
                    result.append("data:image/svg+xml," + quote(svg))
        return tuple(result)

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
                    function(**job['kwargs'])
                    with self._lock:
                        if not self.closed and job['pending_force']:
                            job['pending_force'] = False
                            job['forced'] = True
                            job['kwargs']['force'] = True
                        else:
                            if self._jobs.get(function) is job:
                                self._jobs.pop(function)
                            return
            future = self._pool.submit(run)
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
                self._backend_changed()
            future.add_done_callback(finished)
            return future

    def maintain_caches(self):
        """Check used caches independently of coordinator notification scheduling."""
        with self._lock:
            if self.closed:
                return
            with self.runtime.SETTINGS_LOCK:
                active = self.runtime.STORE
                stores = [active, *(store for store in self.runtime.COUNTRY_STORES.values() if store is not active)]
            for store in stores:
                store.ensure_fresh_async()
            # Only the active and explicitly selected country stores need refreshes.
            # Do not download EPG for unrelated countries every maintenance tick.

    def refresh_active(self):
        """Use the same owned pool for periodic coordinator refreshes."""
        future = self.start_background(self.runtime.STORE.refresh)
        if future is not None:
            future.result()

    def preload_next(self):
        """Warm one inactive country per HA timer tick, keeping active work first."""
        with self._lock:
            if self.closed:
                return
            with self.runtime.SETTINGS_LOCK:
                if any(store.refresh_running for store in self.runtime.COUNTRY_STORES.values()):
                    return
                countries = list(self.runtime.COUNTRIES)
                for _ in countries:
                    country = countries[self._preload_index % len(countries)]
                    self._preload_index += 1
                    if country != self.runtime.STORE.country:
                        break
                store = self.runtime.COUNTRY_STORES.get(country)
                if store is None:
                    store = self.runtime.EPGStore(country)
                    self.runtime.COUNTRY_STORES[country] = store
                if store._cache_fresh():
                    self.runtime.prune_country_stores()
                    return
                store.refresh_running = True
            return self.start_background(store.refresh)

    def request(self, endpoint: str, method: str, body=None):
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
        with self._lock:
            if self.closed:
                raise RuntimeError("TV Guide is unloading")
            if method == "GET" and endpoint == "guide" and isinstance(body, dict) and body.get("known_revision") == f"{self._guide_revision}:{self._guide_generation}":
                return {"unchanged": True, "revision": f"{self._guide_revision}:{self._guide_generation}"}
            if method == "GET" and endpoint == "guide" and self._guide_cache is not None and monotonic() - self._guide_cached_at < 10:
                return self._guide_cache
            if method == "POST":
                self._guide_cache = None
                self._guide_generation += 1
                self._snapshot_cache = None
            started = perf_counter()
            handler = object.__new__(self.runtime.Handler)
            handler.path = "/api/" + endpoint
            handler.headers = {"Content-Length": str(len(encoded))}
            handler.rfile = BytesIO(encoded)
            result = {}
            def capture(payload, status=200):
                if status >= 400:
                    raise ValueError(payload.get("error", "TV Guide request failed"))
                result.update(payload)
            handler._json = capture
            if method == "GET":
                handler.do_GET()
            else:
                handler.do_POST()
            if endpoint == "guide":
                for channel in result.get("channels", []):
                    channel_id = channel.get("source_channel_id") or channel["id"]
                    for programme in channel.get("programs", []):
                        start = datetime.fromisoformat(programme["start"]).astimezone(timezone.utc)
                        key = f"{channel_id}\n{start.isoformat()}"
                        programme["id"] = "guide_" + sha256(key.encode()).hexdigest()
                result["revision"] = f"{self._guide_revision}:{self._guide_generation}"
                self._guide_cache = result
                self._guide_cached_at = monotonic()
                _LOGGER.debug("TV Guide prepared guide in %.1f ms", (perf_counter() - started) * 1000)
            return result

    def snapshot(self):
        store = self.runtime.STORE
        channels = list(store.channels)
        records = [{"channel": channel["id"], "start": item["start"], "stop": item["end"],
                    "title": item["title"], "description": item.get("desc", ""),
                    "subtitle": item.get("subtitle", ""), "category": item.get("category", "")}
                   for channel in channels for item in channel.get("programs", [])]
        catalogue = [{"id": channel["id"], "name": channel["name"], "available": bool(channel.get("programs")),
                      "xmltv_id": channel["id"]} for channel in channels if channel.get("preset")]
        return records, catalogue, [{"id": ch["id"], "name": ch["name"]} for ch in channels]

    def state_snapshot(self):
        """Capture data and active-country status together, outside HA's loop."""
        with self._lock, self.runtime.SETTINGS_LOCK:
            store = self.runtime.STORE
            if self._snapshot_cache is None:
                self._snapshot_cache = self.snapshot()
            records, catalogue, channels = self._snapshot_cache
            return records, catalogue, channels, {
                'country': store.country,
                'refresh_running': store.refresh_running,
                'source_attempts': list(store.source_metrics),
                'last_loaded': store.last_loaded,
                'refresh_minutes': store.options.get('refresh_minutes', 180),
            }

    def close(self):
        with self._lock:
            self.closed = True
        self._pool.shutdown(wait=True, cancel_futures=True)
        sys.modules.pop(self._module_name, None)
