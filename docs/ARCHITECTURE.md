# Native TV Guide architecture

## Repository boundary

Only `criticallimit/HA-TV-Guide` implements this port. `criticallimit/TV-Guide` is the reference add-on and must remain unchanged. The native integration never depends on a hard-coded Docker IP or unauthenticated add-on HTTP endpoint.

## Current runtime

`async_setup_entry` resolves the optional country/custom feed, performs the first coordinator refresh, loads an entry-specific Home Assistant Store and forwards sensor, binary-sensor and calendar platforms. Native actions are shared by the single configured instance. The reminder scheduler uses HA time-event helpers rather than a polling worker. Unload stops timers, removes runtime references and unregisters shared actions when the last relevant entry unloads.

The coordinator downloads one snapshot every three hours. Parsing, decompression and catalogue loading run in the executor. Programmes, parsed feed channels and matched canonical channels are reused by the calendar and response actions. Selected sender IDs live in config-entry options; sender-only changes do not redownload XMLTV.

The five transitional bridge entities mirror optional add-on states using separate registry unique IDs. Native saved-list and EPG entities are independent of those states.

## Native card transport

The manually installed `tv-guide-native-card` custom element uses the `hass` object's existing authenticated WebSocket/service connection. Read actions use `call_service` with `return_response: true`, reading the resulting `response`. Writes use native HA actions. It does not call Ingress, store an access token, fetch a provider directly or modify add-on files.

The card queries a bounded chronological programme window and the existing channel catalogue, with explicit refresh and no timer/subscription. Saved-list reads work without an EPG feed. All feed/config/error text is escaped before DOM rendering. German and English labels and HA theme variables are supported. An original-style multi-channel television grid and automatic frontend registration are later work.

A programme's native ID hashes the feed channel ID and UTC start instant. Names, title text, canonical aliases and timestamp offsets do not determine the ID. These IDs support repeat native save/remove operations; old add-on ID migration needs an explicit mapping policy.

## Storage and reminders

`TVGuideSavedProgrammes` stores bookmarks/reminders in `tv_guide.<entry_id>.saved_programmes`. Records retain old-style field names (`id`, `channel`, `channelId`, `title`, `start`, `end`; reminder metadata adds `minutes`, `language`, `sent`, optionally `sent_at`). Validation removes invalid/expired/duplicate records.

A shared async lock serializes saved actions and notification delivery. `get_saved_programmes` returns independent validated lists without writing or rescheduling timers. Save/remove actions roll back their in-memory lists if persistence raises. Committed changes notify native sensor subscribers and rebuild reminder timers. Sent reminders are not rescheduled; delivery failures retry for a bounded window.

No old storage is read or overwritten. Notification service availability and persistence/delivery interruption behavior still require real HA tests.

## Network and source constraints

Transport uses a dedicated aiohttp connector whose resolver validates the DNS addresses used for the actual connection. Mixed or private addresses are rejected; redirects, environment proxies and automatic HTTP decompression are disabled. HTTPS certificate/hostname validation stays enabled. Incoming bytes, gzip output and parsed programme counts are bounded. This is not a claim of comprehensive transport verification.

Ten country baselines and the original ordered main-channel JSON catalogues are present. Official broadcaster enrichment, alternative source fallback and production-sized feed tests are pending. Third-party EPG/logo rights from the reference add-on still apply; the native card introduces no third-party logo assets.

## Validation boundaries

Offline tests cover parser/policy/selection/query/storage/reminder helpers and saved-action adapters, with HA doubles. Chromium tests exercise the card against a simulated authenticated `hass` connection. GitHub Actions adds HACS/Hassfest and syntax/JSON checks. These checks cannot establish real HA startup, partial platform-forwarding failure rollback, resource installation, country-feed availability or notification delivery. Validate those before recommending an add-on replacement.
