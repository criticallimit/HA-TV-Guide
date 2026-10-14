"""Host the reference programme engine without its server or Supervisor workers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
from io import BytesIO
import json
import logging
from pathlib import Path
import sys
import threading
from urllib.parse import quote
import zipfile

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
                if not target.exists():
                    target.write_bytes(archive.read(name))
        self.closed = False
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tv-guide-native")
        self._jobs = {}
        self._wake = wake
        name = __package__ + ".original_backend._entry_" + storage.name.replace("-", "_")
        self._module_name = name
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "original_backend" / "services.py")
        runtime = importlib.util.module_from_spec(spec)
        runtime.NATIVE_ASSET_ROOT = assets
        runtime.NATIVE_STORAGE_ROOT = storage
        runtime.NATIVE_LOCALE = locale
        runtime.NATIVE_NOTIFICATION_SERVICES = []
        runtime.NATIVE_WAKE = wake
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
        runtime.start_background = self.start_background
        runtime.normalized_logo_urls = self.logo_urls

    def logo_urls(self, channel):
        """Use original bundled main logos; text fallback for additional stations."""
        raw_id = str(channel.get("id") or "")
        country = raw_id.partition(":")[0] if ":" in raw_id else self.runtime.STORE.country
        channel_id = str(channel.get("source_channel_id") or raw_id).split(":")[-1]
        root = Path(__file__).parent / "frontend" / "app" / "logos"
        result = []
        for theme in ("light", "dark"):
            path = root / f"{country}-{channel_id}-{theme}.svg"
            if path.is_file():
                result.append(f"/tv_guide/frontend/app/logos/{quote(path.name)}")
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
                return self._jobs[function]
            future = self._pool.submit(function, **kwargs)
            self._jobs[function] = future
            def finished(job):
                with self._lock:
                    self._jobs.pop(function, None)
                if not job.cancelled():
                    try:
                        job.result()
                    except Exception:
                        _LOGGER.exception("TV Guide provider worker failed")
                self._wake()
            future.add_done_callback(finished)
            return future

    def refresh_active(self):
        """Use the same owned pool for periodic coordinator refreshes."""
        future = self.start_background(self.runtime.STORE.refresh)
        if future is not None:
            future.result()

    def request(self, endpoint: str, method: str, body=None):
        """Dispatch the original route code in-process, without opening HTTP ports."""
        if method == "GET" and endpoint == "refresh":
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
                        programme["id"] = "native_" + sha256(key.encode()).hexdigest()
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

    def close(self):
        with self._lock:
            self.closed = True
        self._pool.shutdown(wait=True, cancel_futures=True)
        sys.modules.pop(self._module_name, None)
