# Native TV Guide architecture

Only HA-TV-Guide implements this port. TV-Guide is pinned read-only reference material.

## Default programme engine

Version 0.3.0 hosts the original programme backend in `original_backend/`, including all source adapters, provider definitions, timeline merging, country caches and mixed-country personal lists. The bundled reference data archive contains the original country/provider/logo metadata and locale catalogues. `OriginalRuntime` supplies entry-owned storage paths and dispatches whitelisted route methods directly, without an HTTP listener. Supervisor locale/options/notification functions and server/daemon-worker entry points are replaced; native HA owns these functions.

`TVGuideOriginalCoordinator` initializes the backend in HA's executor, restores cached data and starts initial source work asynchronously. Original freshness checks submit work to an owned two-worker pool. Source completion wakes the coordinator through the event loop, updating cached calendar/status/action data. Native authenticated `native_request` calls execute original route logic in the executor. Unload closes submissions and drains workers. The original provider policies remain unchanged in this mode; the separate custom-feed coordinator preserves its strict transport and limits.

## Frontend and saved actions

The original HTML/CSS, renderer, fonts, translations and main logos are served by the native integration. Same-origin postMessage routes calls through the embedding card's existing authenticated HA connection. Original-mode guide and sender/settings routes use the reference engine; saved records and notifications use the existing native HA actions and timer scheduler. Full timelines retain artwork URLs and enable original date selection. A stable native programme ID is derived from canonical channel and UTC start.

Native bookmarks/reminders use HA Store and the event-driven scheduler. All previous commit/rollback, stale-timer, expiry and sent-persistence protections remain. Provider caches, preferences and settings live under an entry-owned `.storage/tv_guide_native` directory. Original add-on data is never read or changed. Sensor switches in the legacy settings dialogue stay disabled; HA's entity registry owns native entities.

## Verification and remaining detail work

Inherited provider regression fixtures exercise the copied engine. Existing Python/browser tests cover native storage/reminders and original appearance. CI adds a real HA stable-container startup/actions/reload/unload smoke test with offline provider fixtures. Live provider availability and real notification destinations still require an installation test. Additional station assets use text logos until their full library is packaged; explicit saved-data migration remains separate. Repository privacy/topics currently block HACS publication validation.
