"""Small disk catalogues keep inactive programme caches out of resident memory."""
import json
import os
import tempfile

from .json_files import read_json_file


def _write_index(path, value):
    # Refresh and settings requests may build the same index concurrently.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name, suffix=".tmp", delete=False) as target:
            temporary = target.name
            json.dump(value, target, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _metadata(channels):
    """Recover usable channel metadata without retaining programme timelines."""
    if not isinstance(channels, list):
        return []
    result = []
    for item in channels:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            continue
        channel = {key:value for key,value in item.items() if key != "programs"}
        if not isinstance(channel.get("name"), str) or not channel["name"].strip():
            channel["name"] = channel["id"]
        result.append(channel)
    return result


def write_catalogue(cache_path, country, channels):
    metadata = _metadata(channels)
    _write_index(cache_path.with_suffix(".catalogue.json"), {
        "country": country, "cache_mtime_ns": cache_path.stat().st_mtime_ns,
        "channels": metadata,
    })
    return metadata


def read_catalogue(cache_path, country):
    try:
        stamp = cache_path.stat().st_mtime_ns
        index = read_json_file(cache_path.with_suffix(".catalogue.json"), {})
        if (index.get("country") == country and index.get("cache_mtime_ns") == stamp
                and isinstance(index.get("channels"), list)):
            return _metadata(index["channels"])
        # Upgrade old disk caches once, without creating a resident GuideStore.
        payload = read_json_file(cache_path, {})
        if payload.get("country", "de") != country:
            return []
        channels = payload.get("channels", [])
        if not isinstance(channels, list):
            return []
        metadata = _metadata(channels)
        try:
            # Do not stamp an index as current if a refresh replaced the cache.
            if cache_path.stat().st_mtime_ns == stamp:
                _write_index(cache_path.with_suffix(".catalogue.json"), {
                    "country": country, "cache_mtime_ns": stamp, "channels": metadata,
                })
        except OSError:
            pass
        return metadata
    except OSError:
        return []
