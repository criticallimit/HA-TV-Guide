# Native TV Guide architecture

## Repository boundary

Only `criticallimit/HA-TV-Guide` implements this port. `criticallimit/TV-Guide` is the reference add-on and must remain unchanged. The native integration never depends on a hard-coded Docker IP or unauthenticated add-on HTTP endpoint.

## Current runtime

`async_setup_entry` resolves the optional country/custom feed, performs the first coordinator refresh, loads an entry-specific Home Assistant Store and forwards sensor, binary-sensor and calendar platforms. Native actions are shared by the single configured instance. The reminder scheduler uses HA time-event helpers rather than a polling worker. Unload stops timers, removes runtime references and unregisters shared actions when the last relevant entry unloads.

The coordinator refreshes one snapshot at the configured interval (three hours by default). Germany and Great Britain have sequential primary/EPGShare fallback attempts from the reference configuration. Explicit custom feeds have no fallback. Empty, expired and malformed feeds count as failed attempts; cancellation stops immediately. Every cycle starts at the primary. Only a complete successful attempt replaces channel metadata and the last-success timestamp. The last-refresh sensor exposes the successful source and bounded per-source attempt results; stale snapshots remain unavailable through the coordinator after all-source failure. Parsing, decompression and catalogue loading run in the executor. Programmes, parsed feed channels and matched canonical channels are reused by the calendar and response actions. Selected sender IDs live in config-entry options; sender-only changes do not redownload XMLTV.

The five transitional bridge entities mirror optional add-on states using separate registry unique IDs. Native saved-list and EPG entities are independent of those states.

## Native card transport

The bundled `tv-guide-native-card` custom element uses the `hass` object's existing authenticated WebSocket/service connection. Read actions use `call_service` with `return_response: true`, reading the resulting `response`. Writes use native HA actions. It does not call Ingress, store an access token, fetch a provider directly or modify add-on files.

The card embeds the original frontend from a static native integration path. HTML/CSS, fonts, renderer and normalized catalogue logos retain the reference appearance. A checked same-origin RPC adapter maps the original presentation requests to native HA response/actions; no data HTTP endpoint is introduced. It queries seven rows per displayed sender around the requested time, preserving main and personal lists. The original frontend refreshes cached HA snapshots every five minutes and updates progress every minute, without fetching providers. Saved-list reads work without an EPG feed. All feed/config/error text is escaped before DOM rendering. The original translations and HA theme variables are retained. Static-path registration is async and idempotent across reloads; dashboard resource registration is manual. Pixel-parity tests compare desktop/evening/dark/mobile against a pinned read-only add-on checkout. Multi-country provider aggregation remains pending.

A programme's native ID hashes the feed channel ID and UTC start instant. Names, title text, canonical aliases and timestamp offsets do not determine the ID. These IDs support repeat native save/remove operations; old add-on ID migration needs an explicit mapping policy.

## Storage and reminders

`TVGuideSavedProgrammes` stores bookmarks/reminders in `tv_guide.<entry_id>.saved_programmes`. Records retain old-style field names (`id`, `channel`, `channelId`, `title`, `start`, `end`; reminder metadata adds `minutes`, `language`, `sent`, optionally `sent_at`). Validation removes invalid/expired/duplicate records.

A shared async lock serializes saved actions and notification delivery. `get_saved_programmes` returns independent validated lists without writing or rescheduling timers. Save/remove actions roll back their in-memory lists if persistence raises. Committed changes notify native sensor subscribers and rebuild reminder timers. HA timer callbacks are explicitly marked with `@callback` and stale schedule generations are ignored. Sent reminders are not rescheduled for delivery; delivery failures retry for a bounded window. After successful delivery, a failed sent-state save retries only persistence, so the same loaded scheduler does not resend. Async shutdown drains in-flight deliveries before dropping storage references. A process/power failure before a successful durable write can still cause redelivery after restart; this is not exactly-once delivery.

No old storage is read or overwritten. Notification service availability and persistence/delivery interruption behavior still require real HA tests.

## Network and source constraints

Transport uses a dedicated aiohttp connector whose resolver validates the DNS addresses used for the actual connection. Mixed or private addresses are rejected; redirects, environment proxies and automatic HTTP decompression are disabled. HTTPS certificate/hostname validation stays enabled. Incoming bytes, gzip output and parsed programme counts are bounded. This is not a claim of comprehensive transport verification.

Ten country baselines and the original ordered main-channel JSON catalogues are present. Official broadcaster enrichment and production-sized feed tests are pending. Country-level XMLTV fallback is implemented for the two reference countries with configured alternatives (DE/GB); other countries retain their single baseline. Third-party EPG/logo rights from the reference add-on still apply; the native card reuses the main-channel logo subset with inherited rights notices and font licence.

## Validation boundaries

Offline tests cover parser/policy/selection/query/storage/reminder helpers and saved-action adapters, with HA doubles. Chromium tests exercise the card against a simulated authenticated `hass` connection. GitHub Actions adds HACS/Hassfest and syntax/JSON checks. These checks cannot establish real HA startup, real HA partial platform-forwarding failure rollback, resource installation, country-feed availability or notification delivery. Validate those before recommending an add-on replacement.

## Review fixes

The unsupported `entry.async_unload_callbacks()` call was removed: Home Assistant owns registered on-unload callbacks. Failed/cancelled setup attempts unload partially forwarded platforms while runtime references still exist. Sender-only options notify coordinator listeners to update the calendar without a feed request. Redirect/partial HTTP responses are rejected before parsing, and caller-owned DNS resolvers are explicitly closed. UTF-16/NUL-encoded XML is rejected so DTD checks cannot be bypassed. Saved records sort by UTC instant, and a full saved list rejects new records rather than silently dropping the newest save.

Saved-list expiry and reminder grace-window transitions use one next-boundary timer to commit pruning and refresh count/timestamp entities; no polling worker is added. Subscriber exceptions after a successful Store commit are logged individually and do not turn a committed save into a failed action.
