# Native TV Guide architecture

Only HA-TV-Guide implements this port. TV-Guide is pinned read-only reference material.

## Default programme engine

Version 0.4.4 hosts the original programme backend in `original_backend/`, including all source adapters, provider definitions, timeline merging, country caches and mixed-country personal lists. The bundled reference data archive contains the original country/provider/logo metadata and locale catalogues. `OriginalRuntime` supplies entry-owned storage paths and dispatches whitelisted route methods directly, without an HTTP listener. Supervisor locale/options/notification functions and server/daemon-worker entry points are replaced; native HA owns these functions.

`TVGuideOriginalCoordinator` initializes the backend in HA's executor, restores cached data and starts initial source work asynchronously. Original freshness checks submit work to an owned two-worker pool. Source completion wakes the coordinator through the event loop, updating cached calendar/status/action data. Native authenticated `native_request` calls execute original route logic in the executor. Unload closes submissions and drains workers. The original provider policies remain unchanged in this mode; the separate custom-feed coordinator preserves its strict transport and limits.

## Frontend and saved actions

The original HTML/CSS, renderer, fonts, translations and main logos are served by the native integration. Same-origin postMessage routes calls through the embedding card's existing authenticated HA connection. Original-mode guide and sender/settings routes use the reference engine; saved records and notifications use the existing native HA actions and timer scheduler. Full timelines retain artwork URLs and enable original date selection. A stable native programme ID is derived from canonical channel and UTC start.

Native bookmarks/reminders use HA Store and the event-driven scheduler. All previous commit/rollback, stale-timer, expiry and sent-persistence protections remain. Provider caches, preferences and settings live under an entry-owned `.storage/tv_guide_native` directory. Original add-on data is never read or changed. Native sensors are created automatically; their entity management remains in Home Assistant. Manual dashboard setup and sensor switches are omitted from the TV Guide settings.

## Verification and remaining detail work

Inherited provider regression fixtures exercise the copied engine. Existing Python/browser tests cover native storage/reminders and original appearance. CI adds a real HA stable-container startup/actions/reload/unload smoke test with offline provider fixtures. Live provider availability and real notification destinations still require an installation test. The complete source logo library is packaged locally; saved records exist exclusively in the native HA Store. Repository privacy/topics currently block HACS publication validation.

Repeated refresh requests share one queued/running job per country store. Periodic coordinator refreshes use the same owned worker pool, so unload drains those requests as well. Native option restoration tolerates corrupt/wrong-root JSON and writes the replacement atomically. Live DE/GB engine checks passed on 14 October 2026; actual HA runtime verification remains fixture-backed.

## Automatic installation

Config flow version 2 immediately creates an entry from HA country/language with no user fields or options form. Locale fallback rules are pure and tested. Version 1 entries without an explicit custom feed are migrated automatically; legacy explicit feeds are retained. The frontend dependency loads a native sidebar panel and extra card module on setup, removing owned UI registrations on unload. Static code registration remains idempotent across reloads. The sidebar panel passes HA state to the original-style card; no manual resource registration is required.

## Port audit fixes

An owned HA interval timer checks one inactive country every 120 seconds, deferring while country refreshes are busy. Fresh caches are reused; stale caches use the same deduplicated worker pool and are pruned from memory after refresh. Unload cancels the timer and drains workers. Data and active-country status are captured together outside HA's event loop; country switches clear absent last-update timestamps, malformed timestamps report unknown, and worker wakes arriving during synchronization request another snapshot. Extracted bundled reference data is repaired/updated atomically on restart.

Both settings action paths persist normalized engine values and update the reminder destination. Native reminder count/success/time semantics match the original sensors, while state bridge code is completely removed. Test notification text uses the original frontend translations and HA timezone. Notification choices match the original Home Assistant/mobile-app targets.

## Standalone data and logos

No runtime discovers or reads an installed add-on. State bridges, source entity constants, old browser-bookmark imports, duplicate reference bookmark/reminder routes and Supervisor option/notification helpers are removed. Native config-entry version upgrades concern earlier versions of this integration only.

The logo index contains all 20,292 original image paths, mapped to 18,528 verified SHA-256 objects in 37 ZIP bundles. The native HA view serves only indexed public artwork and performs ZIP reads/normalization in the executor. Europe SVG raster dependencies are embedded in the response, matching the reference rendering. Main-channel static SVGs remain unchanged for pixel parity. No logo downloads or add-on webserver are used.
