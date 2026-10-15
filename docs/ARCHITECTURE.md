# TV Guide integration architecture

Only HA-TV-Guide implements this port. TV-Guide is pinned read-only reference material.

## Default programme engine

TV Guide hosts the original programme backend in `original_backend/`, including all source adapters, provider definitions, timeline merging, country caches and mixed-country personal lists. The bundled reference data archive contains the original country/provider/logo metadata and locale catalogues. `GuideRuntime` supplies entry-owned storage paths and dispatches whitelisted route methods directly, without an HTTP listener. Supervisor locale/options/notification functions and server/daemon-worker entry points are replaced; native HA owns these functions.

`TVGuideCoordinator` initializes the backend in HA's executor, restores cached data and starts initial source work asynchronously. Original freshness checks submit work to an owned two-worker pool. Source completion wakes the coordinator through the event loop, updating cached calendar/status/action data. Native authenticated `guide_request` calls execute original route logic in the executor. Unload closes submissions and drains workers. The original provider policies remain unchanged in this mode; the separate custom-feed coordinator preserves its strict transport and limits.

## Frontend and saved actions

The original HTML/CSS, renderer, fonts, translations and main logos are served by the native integration. Same-origin postMessage routes calls through the embedding card's existing authenticated HA connection. Original-mode guide and sender/settings routes use the reference engine; saved records and notifications use the existing native HA actions and timer scheduler. Full timelines retain artwork URLs and enable original date selection. A stable native programme ID is derived from canonical channel and UTC start.

Native bookmarks/reminders use HA Store and the event-driven scheduler. All previous commit/rollback, stale-timer, expiry and sent-persistence protections remain. Provider caches, preferences and settings live under an entry-owned `.storage/tv_guide_store` directory. Original add-on data is never read or changed. Native sensors are created automatically; their entity management remains in Home Assistant. Manual dashboard setup and sensor switches are omitted from the TV Guide settings.

## Verification and remaining detail work

Inherited provider regression fixtures exercise the copied engine. Existing Python/browser tests cover native storage/reminders and original appearance. CI adds a real HA stable-container startup/actions/reload/unload smoke test with offline provider fixtures. Live provider availability and real notification destinations still require an installation test. The complete source logo library is packaged locally; saved records exist exclusively in the native HA Store.

Repeated refresh requests share one queued/running job per country store. Periodic coordinator refreshes use the same owned worker pool, so unload drains those requests as well. Native option restoration tolerates corrupt/wrong-root JSON and writes the replacement atomically. Live DE/GB engine checks passed on 14 October 2026; actual HA runtime verification remains fixture-backed.

## Automatic installation

Config flow version 2 immediately creates an entry from HA country/language with no user fields or options form. Locale fallback rules are pure and tested. The frontend dependency loads a native sidebar panel and extra card module on setup, removing owned UI registrations on unload. Static code registration remains idempotent across reloads. The sidebar panel passes HA state to the original-style card; no manual resource registration is required.

## Port audit fixes

An owned HA interval timer checks one inactive country every five minutes, deferring while country refreshes are busy. Fresh caches are reused; stale caches use the same deduplicated worker pool and are pruned from memory after refresh. Unload cancels the timer and drains workers. Data and active-country status are captured together outside HA's event loop; country switches clear absent last-update timestamps, malformed timestamps report unknown, and worker wakes arriving during synchronization request another snapshot. Extracted bundled reference data is repaired/updated atomically on restart.

Both settings action paths persist normalized engine values and update the reminder destination. Native reminder count/success/time semantics match the original sensors, while state bridge code is completely removed. Test notification text uses the original frontend translations and HA timezone. Notification choices match the original Home Assistant/mobile-app targets.

## Standalone data and logos

The integration does not discover or read a separately installed TV Guide instance. State bridges, source entity constants, old browser-bookmark imports, duplicate reference bookmark/reminder routes and Supervisor option/notification helpers are removed. 

The logo index contains all 20,292 original image paths, mapped to 18,528 verified SHA-256 objects in 37 ZIP bundles. The native HA view serves only indexed public artwork and performs ZIP reads/normalization in the executor. Europe SVG raster dependencies are embedded in the response, matching the reference rendering. Main-channel static SVGs remain unchanged for pixel parity. No logo downloads or add-on webserver are used.

## Readiness audit

The five-minute maintenance timer checks active and retained country caches before inactive preloading. This guarantees freshness even when frequent data/status notifications reschedule the DataUpdateCoordinator timer. Forced requests arriving during non-forced work request one forced follow-up within the same owned job; duplicate already-forced requests remain deduplicated. Shutdown rejects new requests and chunk reads cooperatively, preserving the original network policies; a currently blocked IO call still observes its provider timeout.

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
