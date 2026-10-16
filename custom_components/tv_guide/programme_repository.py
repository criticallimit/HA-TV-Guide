"""Shared public programme projections, rebuilt only when source data change."""
from datetime import datetime, timezone
from hashlib import sha256
import threading
from weakref import WeakKeyDictionary


class ProgrammeRepository:
    def __init__(self):
        self._lock = threading.RLock()
        self._generation = 0
        self._stores = WeakKeyDictionary()

    def clear(self):
        with self._lock:
            self._generation += 1
            self._stores.clear()

    def programmes(self, store, channel):
        raw = channel.get('programs')
        if not isinstance(raw, list):
            raw = ()
        key = channel['id']
        with self._lock:
            generation = self._generation
            cached = self._stores.get(store, {}).get(key)
            if cached is not None and cached[0] is raw and cached[1] == len(raw):
                return cached[2]
        public = []
        for item in store._validate_program_timeline(raw):
            value = {name: data for name, data in item.items() if not str(name).startswith('_')}
            value['source'] = item.get('_source_url') or item.get('_source')
            value['source_kind'] = item.get('_source_kind') or 'unknown'
            start = datetime.fromisoformat(item['start']).astimezone(timezone.utc)
            value['id'] = 'guide_' + sha256(f'{key}\n{start.isoformat()}'.encode()).hexdigest()
            public.append(value)
        with self._lock:
            if generation == self._generation:
                self._stores.setdefault(store, {})[key] = (raw, len(raw), public)
        return public


def compact_guide(payload):
    """Transfer each station's timeline once even when used by several views."""
    if payload.get('unchanged'):
        return payload
    programmes, channels, identities = {}, [], {}
    for channel in payload.get('channels', []):
        rows = channel.get('programs', [])
        identity = (channel.get('source_country') or payload.get('country'),
                    channel.get('source_channel_id') or channel['id'], len(rows),
                    rows[0].get('id') if rows else None, rows[-1].get('id') if rows else None)
        reference = identities.get(identity)
        if reference is None or programmes[reference] != rows:
            reference = str(len(programmes))
            identities[identity] = reference
            programmes[reference] = rows
        channels.append({**{key:value for key,value in channel.items() if key != 'programs'},
                         'programme_set':reference})
    return {**payload, 'channels':channels, 'programme_sets':programmes}
