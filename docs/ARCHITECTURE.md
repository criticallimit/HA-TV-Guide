# TV Guide integration architecture

Only HA-TV-Guide implements this port. TV-Guide is pinned read-only reference material.

## Default programme engine

TV Guide hosts the original programme backend in `original_backend/`, including all source adapters, provider definitions, timeline merging, country caches and mixed-country personal lists. The bundled reference data archive contains the original country/provider/logo metadata and locale catalogues. `GuideRuntime` supplies entry-owned storage paths and dispatches whitelisted route methods directly, without an HTTP listener. Supervisor locale/options/notification functions and server/daemon-worker entry points are replaced; native HA owns these functions.

`TVGuideCoordinator` initializes the backend in HA's executor, restores cached data and starts initial source work asynchronously. Original freshness checks submit work to an owned two-worker pool. Source completion wakes the coordinator through the event loop, updating cached calendar/status/action data. Native authenticated `guide_request` calls execute original route logic in the executor. Unload closes submissions and drains workers. The original provider policies remain unchanged in this mode; the separate custom-feed coordinator preserves its strict transport and limits.

## Frontend and saved actions

The native Lovelace component renders scoped HTML/CSS, renderer, fonts, translations and main logos directly in its Shadow DOM. Per-card module factories call the card's existing authenticated HA connection directly; there is no embedded document, message bridge or simulated HTTP transport. Original-mode guide and sender/settings routes use the reference engine; saved records and notifications use the existing native HA actions and timer scheduler. Full timelines retain artwork URLs and enable original date selection. A stable native programme ID is derived from canonical channel and UTC start.

Native bookmarks/reminders use HA Store and the event-driven scheduler. All previous commit/rollback, stale-timer, expiry and sent-persistence protections remain. Provider caches, preferences and settings live under an entry-owned `.storage/tv_guide_store` directory. Original add-on data is never read or changed. Native sensors are created automatically; their entity management remains in Home Assistant. Manual dashboard setup and sensor switches are omitted from the TV Guide settings.

## Verification and remaining detail work

Inherited provider regression fixtures exercise the copied engine. Existing Python/browser tests cover native storage/reminders and original appearance. CI adds a real HA stable-container startup/actions/reload/unload smoke test with offline provider fixtures. Live provider availability and real notification destinations still require an installation test. The complete logo index and main-channel logos are bundled; the large library archives download after installation. Saved records exist exclusively in the native HA Store.

Repeated refresh requests share one queued/running job per country store. Periodic coordinator refreshes use the same owned worker pool, so unload drains those requests as well. Native option restoration tolerates corrupt/wrong-root JSON and writes the replacement atomically. Live DE/GB engine checks passed on 14 October 2026; actual HA runtime verification remains fixture-backed.

## Automatic installation

Config flow version 2 immediately creates an entry from HA country/language with no user fields or options form. Locale fallback rules are pure and tested. The frontend dependency loads a native sidebar panel and extra card module on setup, removing owned UI registrations on unload. Static code registration remains idempotent across reloads. The sidebar panel passes HA state to the original-style card; no manual resource registration is required.

## Port audit fixes

An owned HA interval timer checks the active country and countries used by My Channels every five minutes. Fresh caches and refresh backoff are reused; stale caches use the same deduplicated worker pool. Unselected idle stores are pruned instead of warming all countries. Unload cancels the timer and drains workers. Data and active-country status are captured together outside HA's event loop; country switches clear absent last-update timestamps, malformed timestamps report unknown, and worker wakes arriving during synchronization request another snapshot. Extracted bundled reference data is repaired/updated atomically on restart.

Both settings action paths persist normalized engine values and update the reminder destination. Native reminder count/success/time semantics match the original sensors, while state bridge code is completely removed. Test notification text uses the original frontend translations and HA timezone. Notification choices match the original Home Assistant/mobile-app targets.

## Standalone data and logos

The integration does not discover or read a separately installed TV Guide instance. State bridges, source entity constants, old browser-bookmark imports, duplicate reference bookmark/reminder routes and Supervisor option/notification helpers are removed.

The logo index contains all 20,292 original image paths, mapped to 18,528 verified SHA-256 objects in 37 ZIP bundles. These archives download from the integration's own immutable GitHub source into entry-owned storage after installation, with size and SHA-256 verification, resume and repair. The native HA view serves only indexed public artwork and performs ZIP reads/normalization in the executor. Europe SVG raster dependencies are embedded in the response, matching the reference rendering. Main-channel static SVGs remain unchanged for pixel parity. No installed add-on or add-on webserver is used. See `LOGO_DOWNLOAD.md` for preparation progress and retry behavior.

## Readiness audit

The five-minute maintenance timer checks active and retained country caches. Unselected, idle country stores are released instead of warming every country in a separate worker. This guarantees freshness even when frequent data/status notifications reschedule the DataUpdateCoordinator timer. Forced requests arriving during non-forced work request one forced follow-up within the same owned job; duplicate already-forced requests remain deduplicated. Shutdown rejects new requests and chunk reads cooperatively, preserving the original network policies; a currently blocked IO call still observes its provider timeout.

Restored native cache records are checked for valid aware date ranges and metadata containers before use. Good rows survive a partially damaged cache. Calendar label lookup happens once per snapshot/range, avoiding a catalogue scan for every programme. Main logos use their own country prefix when another country is active. Browser pixel comparisons now include all ten countries and all eight interface languages.

The sidebar sizes the guide to available viewport height in portrait and landscape. Card heights are finite, bounded values; invalid configuration values fall back to 1000 pixels.

## Follow-up review

Named card themes retain the original visual editor, HA mode values and dashboard inheritance. Short CSS hex colours also determine light/dark appearance correctly. Native programme response actions scan and sort snapshots in the HA executor instead of blocking the event loop. The public logo route handles corrupt ZIP bundles as missing images rather than leaking HTTP 500 errors.

## Manual installation review

Distribution uses manual installation of the complete custom component directory. CI validates the native integration with offline unit/JSON/syntax checks, Hassfest, browser parity and a real Home Assistant smoke test. Calendar range queries capture the current snapshot and selection, then build/filter/sort events in HA's executor. The smoke also exercises the native calendar get_events action.

## Complete action review

The native get_guide action validates optional aware timestamps and returns a copied seven-row window when requested; default original-provider timelines remain complete for date navigation. HA reminder select fields may supply numeric strings, which are normalized to supported integer values; fractional and boolean minute values are rejected. Saved channel identifiers share a 200-character bound across the action schema and storage, preserving country-qualified XMLTV identifiers.

## Full lifecycle and boundary review

Unchanged HA state updates reuse the existing Lovelace theme selector instead of rebuilding its focused control. Refresh-state callbacks are isolated so one failed subscriber cannot abort a programme refresh or prevent other entities from updating. Reminder delivery and retry deadlines end at the earlier of programme end and the five-minute grace limit. Unrepresentable UTC conversions are rejected in saved records, provider/XMLTV parsing, restored caches and timeline validation; valid rows are retained. All reminder arithmetic handles datetime range overflow without breaking setup or scheduling.

## Conditional guide reads and cancellation

The card forwards its known guide revision through the authenticated `guide_request` action. An unchanged reply keeps the short refresh-completion timer running while providers are busy; completed refreshes invalidate the revision and deliver a complete replacement. Cropped first-paint browser snapshots never opt into conditional reads until a complete response has arrived.

Backend construction runs in an owned shielded startup task. Cancelling setup leaves the constructor owned by the coordinator; shutdown waits for it and closes its worker pool, without starting timers or provider work after shutdown. Concurrent and cancelled shutdown waiters still share the same cleanup task.

## First display

The card immediately renders its toolbar and scoped view, then requests an authenticated seven-row guide preview. It paints this response before requesting complete timelines in the background. Preview windows use the configured default time in the browser's time zone, preserve programme details, and never claim to hold a complete revision. Time/date navigation keeps the existing renderer and uses the full timelines once loaded. See `PERFORMANCE.md` for bounds and verification.

## Native cleanup and HA acceptance

The unused backend-mode flag is removed from existing config entries and runtime
options without changing country, language or presentation preferences. Obsolete
HTTP file-serving methods, the replaced logo normalizer and unused country
preload loops are removed. Native indexed logo serving, owned workers and
maintenance of selected countries remain. Historical entity unique IDs are kept
to preserve the existing entity registry. Explicit XMLTV feeds remain compatible.

The actual HA runtime test also exercises authenticated WebSocket services,
rejected inputs, all ten countries and four default times in two time zones,
next-day windows, scheduled persistent-notification delivery with on-disk sent
state, duplicate suppression, three reload cycles and complete removal.

## Native view ownership

The sidebar hosts the same Lovelace component. Theme and language updates only
change the view when their values change. Resize observers batch layout work
through animation frames. Disconnecting a card cancels its pending requests,
timers, listeners and observers; the retained guide is reduced to seven upcoming
programmes per channel at the selected time. Reconnecting preserves the DOM and
selection and reloads complete timelines without claiming a complete revision.

The original standalone frontend under `tests/reference-frontend` is an immutable
pixel-comparison fixture, not shipped runtime code. Its original embedding and
message handling are intentionally preserved so the comparison stays independent.

## Configuration upgrades and concurrent writes

Version-one config entries migrate to version two with their entry ID, explicit
XMLTV URL, sender selection and notification destination preserved. The obsolete
backend flag is removed; newer unsupported config versions are not downgraded.
Concurrent partial settings actions serialize the backend read/modify/write and
HA option persistence, so unrelated changes do not overwrite each other.

Explicit XMLTV responses carry `_windowed: true`: they contain seven programme
rows per channel, and the card requests the selected time window on date/time
navigation. Complete provider timelines continue to navigate locally. XMLTV
station IDs over the supported 160-character limit are skipped consistently in
metadata and programmes, rather than truncated into another station's ID.

## XMLTV identity and preference recovery

Canonical main-channel IDs take precedence over additional raw feed IDs in both
presentation and action catalogues. A feed alias cannot replace an already mapped
main channel or create duplicate selection keys. Each configured alias prefers
its exact XMLTV ID; a case-insensitive match is accepted only when it identifies
one feed station, independent of feed ordering.

Legacy sender order and hidden lists recover from malformed field types and skip
invalid entries while preserving valid preferences. Reads do not rewrite the
source preference file.

## Retry recovery and inactive-country metadata

A failed guide read remains pending across a brief tab switch. Becoming visible
retries it even when the last successful guide is less than a minute old; a
successful response clears that failure state. Hidden views still do not poll.

Small inactive-country catalogue files validate station IDs, recover missing
names from their IDs and discard programme timelines. Malformed catalogue rows
cannot prevent the sender picker from loading or retain full EPG data in memory.
