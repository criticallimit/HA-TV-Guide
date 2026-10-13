# Native TV Guide integration architecture

## Current implementation

The integration is a **setup-only preview**. It has an initial config flow and
does not yet expose entities, connect to EPG providers or communicate with the
existing add-on. Do not disable the add-on.

## Existing add-on transport

The add-on runs a `ThreadingHTTPServer` on port 8099 with Supervisor Ingress.
Endpoints in `tv-guide/tvguide/api.py` include:

- `GET /api/status`: cache/refresh status
- `GET /api/reminders`: reminders
- `GET /api/bookmarks`: saved programmes
- `GET /api/guide`: programme data
- `GET /api/settings`: add-on options

These are designed for use through Ingress, not as a general-purpose
authenticated Home Assistant integration API. The integration must **not**
assume it can access the Supervisor ingress proxy or use a hard-coded private
Docker IP. Exposing the existing unauthenticated backend on a public port would
be unsafe.

## Planned safe bridge

1. Identify a supported authenticated integration-to-add-on transport, or
   implement the standalone EPG engine directly in the integration.
2. Reuse Home Assistant's shared HTTP session and nonblocking execution.
3. Create a `DataUpdateCoordinator` to coalesce reads and avoid duplicated
   EPG downloads.
4. Register native entities with stable unique IDs and use the entity
   registry. Ensure old REST-published state-only entity IDs do not collide.
5. Keep add-on reminders, bookmark persistence and the Lovelace card working.
6. Test installation, unloading, authentication, service failures and upgrades.

## Native entities planned

- `sensor.tv_guide_next_reminder`
- `sensor.tv_guide_bookmark_count`
- `sensor.tv_guide_reminder_count`
- `sensor.tv_guide_last_update`
- `binary_sensor.tv_guide_refresh_running`

All five already exist as optional **REST-published states** in the add-on;
they are not yet registry-backed integration entities.

The integration should not publish duplicate entity IDs while the add-on
sensor options are active.

## Source constraints

The EPG data and locally bundled third-party logos have rights and
redistribution constraints described in the original repository's
`THIRD_PARTY_NOTICES.md`. Native integration publication and possible Core
submission require separate review.

## Experimental native EPG downloader

`epg_client.py` and `coordinator.py` provide an isolated, **not yet activated** HTTPS XMLTV fetcher and a shared 3-hour refresh coordinator. Redirects are disabled, incoming data is bounded to 12 MiB, and gzip decoding and XML parsing run in the Home Assistant executor. The 8 MiB decompressed data limit is deliberately conservative and may reject large country feeds.

These modules are **not wired into the configuration flow or setup**. No URL is configured and no additional background downloads occur until that wiring, security review, and tests are completed. The integration still relies on add-on-published states for its five entities.

Before enabling network access, add explicit feed selection, protection against local/private-network endpoints and DNS rebinding, end-to-end tests, and review of data-source terms.

## DNS policy development

`dns_policy.py` now validates resolved DNS records, rejecting the entire
response when **any** returned address is non-public. The policy has offline
tests for mixed public/private results, loopback, link-local and malformed
answers.

**This is only the validation component.** It is not yet wired to the
transport. In particular, a DNS preflight followed by an ordinary aiohttp
request is insufficient against DNS rebinding: the dedicated HTTP connector
must use the validated address selection for its actual connection and prevent
later resolution from bypassing the policy. HTTPS hostname and certificate
validation must remain enabled. The downloader stays disconnected from
Home Assistant setup pending that work.
