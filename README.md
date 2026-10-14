# TV Guide – Native Home Assistant Integration

**Development preview.** This repository (`HA-TV-Guide`) contains the native custom integration and its native dashboard card. The existing [TV Guide add-on](https://github.com/criticallimit/TV-Guide) is a separate project and is not modified by this port.

## Current capabilities

- Optional standalone HTTPS XMLTV source, with ten experimental country baselines (DE, AT, CH, NL, BE, DK, NO, FR, SE and GB).
- One shared EPG snapshot, normally refreshed every three hours, a read-only programme calendar, channel catalogue and native EPG status entities.
- Original ordered country channel catalogues, canonical sender ID mapping and persistent personal sender selection.
- Native bookmarks and reminders in Home Assistant `.storage`; event-driven delivery through `persistent_notification.create` or a configured `notify.*` service.
- Native bookmark/reminder count and next-reminder entities, independent of the add-on.
- An experimental **TV Guide Native** dashboard card for programme browsing, sender selection/order, bookmarks and reminders, using Home Assistant's authenticated connection.
- Five optional state mirrors of the original add-on for the transitional bridge. These have separate unique IDs and names.

This is not yet a complete replacement for the add-on: provider fallbacks/enrichment, the original television grid, logos/artwork, old saved-data migration and full UI parity are pending. Keep the add-on available while testing. No production readiness or live Home Assistant compatibility is implied by offline tests.

## Manual integration installation

1. Back up Home Assistant.
2. Copy the complete `custom_components/tv_guide` folder to `/config/custom_components/tv_guide`.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → TV Guide**.
5. Choose a country baseline or enter a public HTTPS XMLTV feed URL. A custom URL overrides the country baseline. Leave both blank for bridge-only operation.

The initial feed is downloaded during setup. A failed download leaves the entry not ready for Home Assistant to retry. The download is limited to 12 MiB on the wire and 8 MiB after decompression, with at most 50,000 parsed programmes; large country feeds may exceed these preview limits. Only configure sources you are authorized to access.

**Configure** allows changing country/feed, selected canonical or XMLTV IDs (maximum 200) and notification destination. Changing only sender selection/order or notification destination does not redownload the feed. Changing the EPG source reloads the entry.

Updating requires copying the new integration folder and restarting Home Assistant; a GitHub commit does not deploy to your installation.

## Install the native dashboard card

The native card has a separate element and resource name so it can coexist with the add-on card.

1. Copy `custom_components/tv_guide/frontend/tv-guide-native-card.js` to `/config/www/tv-guide-native-card.js` (create `www` if necessary).
2. Restart Home Assistant if you just created `www`.
3. In **Settings → Dashboards → Resources** (advanced mode), add `/local/tv-guide-native-card.js?v=1` as **JavaScript module**.
4. Add **TV Guide Native** from the card picker, or use a manual card:

```yaml
type: custom:tv-guide-native-card
title: TV Guide
```

Do not replace the add-on's `tv-guide-card.js` or its loader. On updates, copy the native resource again and change the `v=` suffix to refresh browser caches. Automatic resource registration and a sidebar panel are not implemented yet.

The native card reads the cached EPG and does not request an EPG download. It offers a chronological schedule with sender filtering and 3/6/12/24-hour windows. **Earlier / Now / Later** move the time window; broadcast times use Home Assistant's configured time zone. At most 500 programmes are returned, with a visible notice when more match. Refresh explicitly reloads the card's data; automatic cross-client updates are pending.

**My channels** selects and reorders canonical senders and extra feed channels. A sender without EPG remains visible; it does not silently turn into an all-channel query. **All channels** resets the stored selection. An empty saved selection means all channels, not zero channels.

Programme actions save native bookmarks or reminders with 5/10/15/30-minute advance offsets. Saved lists show future/active programmes and allow removal. Existing reminders display their sent status. Programme IDs are derived from the feed channel ID and UTC start instant, so repeated card saves refer to the same native item. These IDs are not a promise of compatibility with old add-on bookmarks; migration is still separate.

The card follows Home Assistant's theme variables and supports German and English (English fallback). It accesses neither Supervisor Ingress nor the add-on HTTP API, and needs no separately stored access token.

## Native actions

- `tv_guide.get_programmes`: response-only cached programme query, with offset-aware `start`/`end`, optional `channel_id` and `limit` (1–500). Maximum range: seven days. Returns `programmes`, `count` and `truncated`; each record includes a stable native `id`.
- `tv_guide.get_channels`: response-only catalogue including availability and saved sender order/selection.
- `tv_guide.set_channels`: persist an ordered list in `channels`; `[]` means all.
- `tv_guide.get_saved_programmes`: response-only `bookmarks` and `reminders`, filtering expired records without writing storage. Also available with no EPG source.
- `tv_guide.save_bookmark` / `tv_guide.save_reminder`: accept `id`, `title`, `channel`, `channel_id`, offset-aware ISO `start` and `end`; reminders also accept `minutes`.
- `tv_guide.remove_saved_programme`: accepts `id` and `kind` (`bookmark` or `reminder`).

These actions currently require exactly one loaded entry/feed as applicable. A storage failure rolls back the saved-list action's in-memory changes. Reminder delivery failures remain pending and retry within the existing bounded delivery window; sent reminders are not rearmed on restart. Notification delivery itself still needs testing in a running Home Assistant.

## Optional add-on state bridge

To test the five bridge entities, keep the add-on running and enable its optional sensors under **Settings → Advanced → Available sensors**. The integration listens to these states without polling. Missing or disabled source states leave the bridge entities unavailable. Existing automations should continue using their original IDs during migration; native IDs deliberately differ.

Fresh native bookmark/reminder storage is empty. The integration does not read or overwrite add-on files, and the native counts may differ from the add-on counts.

## Validation and remaining work

Local validation for the native-card change: 50 Python offline tests passed; five Chromium workflow scenarios passed (including sender ordering, saved-item actions, service errors, unavailable EPG, feed-text escaping, language and reconnect). Tests use HA doubles; they do not run a real HA server. The suite now loads pure Python helpers without inserting the integration directory into `sys.path`, avoiding accidental shadowing of Python's `calendar` module.

GitHub Actions runs offline tests, Python/JSON validation, HACS, Hassfest and Chromium card tests. Check the actual results for the branch/PR; local success does not establish CI success.

Before replacing the add-on, test real HA installation/reload/unload, country feed sizes and availability, mobile-notification delivery, storage failures, and card setup on desktop/mobile. Provider fallback/enrichment, original UI parity and explicit old-data migration remain required. See [architecture](docs/ARCHITECTURE.md) and [manual test steps](docs/NATIVE_CARD_TESTING.md).

## Licence

MIT covers project-authored source code. External programme data, logos and broadcaster marks are not covered by it; consult the add-on's third-party notices. This native card does not bundle logo assets.
