# TV Guide – Native Home Assistant Integration

**Development preview.** This repository (`HA-TV-Guide`) contains the native custom integration and its native dashboard card. The existing [TV Guide add-on](https://github.com/criticallimit/TV-Guide) is a separate project and is not modified by this port.

## Current capabilities

- Optional standalone HTTPS XMLTV source, with ten experimental country baselines (DE, AT, CH, NL, BE, DK, NO, FR, SE and GB).
- One shared EPG snapshot, normally refreshed every three hours (configurable in the native UI), a read-only programme calendar, channel catalogue and native EPG status entities.
- Original ordered country channel catalogues, canonical sender ID mapping and persistent personal sender selection.
- Native bookmarks and reminders in Home Assistant `.storage`; event-driven delivery through `persistent_notification.create` or a configured `notify.*` service.
- Native bookmark/reminder count and next-reminder entities, independent of the add-on.
- An experimental **TV Guide Native** dashboard card retaining the original add-on presentation for programme browsing, sender selection/order, bookmarks and reminders, using Home Assistant's authenticated connection.
- Five optional state mirrors of the original add-on for the transitional bridge. These have separate unique IDs and names.

This is not yet a complete replacement for the add-on: provider fallbacks/enrichment, provider-specific programme artwork, old saved-data migration and multi-country provider aggregation are pending. Keep the add-on available while testing. No production readiness or live Home Assistant compatibility is implied by offline tests.

## Manual integration installation

1. Back up Home Assistant.
2. Copy the complete `custom_components/tv_guide` folder to `/config/custom_components/tv_guide`.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → TV Guide**.
5. Choose a country baseline or enter a public HTTPS XMLTV feed URL. A custom URL overrides the country baseline. Leave both blank for bridge-only operation.

The initial feed is downloaded during setup. A failed download leaves the entry not ready for Home Assistant to retry. The download is limited to 12 MiB on the wire and 8 MiB after decompression, with at most 50,000 parsed programmes; large country feeds may exceed these preview limits. Only configure sources you are authorized to access.

**Configure** allows changing country/feed, selected canonical or XMLTV IDs (maximum 200) and notification destination. Changing only sender selection/order or notification destination does not redownload the feed. Changing the EPG source or refresh interval reloads the entry.

Updating requires copying the new integration folder and restarting Home Assistant; a GitHub commit does not deploy to your installation.

## Install the native dashboard card

The native integration serves the complete bundled card itself. No copy to `/config/www` is required.

1. Install/update the integration folder and restart Home Assistant.
2. Under **Settings → Dashboards → Resources** (advanced mode), add `/tv_guide/frontend/tv-guide-native-card.js?v=2` as **JavaScript module**.
3. Add **TV Guide Native**, or configure a manual card:

```yaml
type: custom:tv-guide-native-card
height: 1000
```

Optional `theme` and height settings match the original card (height 500–2200). If you previously installed the preview `/local/tv-guide-native-card.js` resource, replace that resource URL with the new native URL. Keep the original add-on card and its loader unchanged. After updates, increment the `v=` suffix or refresh browser caches.

**Appearance follows the add-on.** The native card reuses the original HTML layout, CSS, programme renderer, sender picker, translations, Source Sans Pro fonts and theme-specific normalized main-channel logos. The turquoise toolbar, Jetzt / 18:00 / 20:15 / 22:00 / Andere Zeiten controls, sender columns, seven programme rows, current-programme progress, saved-list and programme-detail dialogues retain the original presentation. The initial independent timeline/list prototype has been replaced.

A pinned original reference is recorded in `frontend/app/REFERENCE.json`. Browser tests compare screenshots for identical data: desktop, 20:15, dark theme and mobile match pixel for pixel. This verifies visual equivalence for those fixtures, not equivalence of provider data or every installation/theme.

The inner view is served from the native integration and communicates only with its embedding card via checked same-origin messages. The card uses Home Assistant's authenticated connection; it makes no Supervisor, Ingress or add-on API requests and stores no separate access token. Only public static presentation code and logos are served over the HTTP asset path; saved programmes and EPG require native authenticated actions.

Native bookmark IDs remain stable across title/name changes. Removing a saved programme from the original-style list atomically removes its bookmark and associated reminder. Native browser caches use separate keys; automatic import of the add-on's browser/storage data is disabled.

The sender picker currently covers the configured country's catalogue and the current feed's extra channels. Multi-country provider aggregation and the old add-on's source enrichment are pending. Display is bounded to 200 senders per list and seven rows per sender; other-time selection queries the cached native snapshot. Native registry-backed sensors are managed through Home Assistant's entity settings, so legacy sensor switches in the copied settings dialogue are disabled. UI settings persist language, view, theme mode, column count, maximum displayed senders, refresh interval and notification destination in config-entry options. Resource setup still requires the one manual dashboard registration.

## Native actions

- `tv_guide.get_native_guide` / `get_native_channels`: bounded presentation snapshots for the original-style card, with no extra EPG download.
- `tv_guide.get_ui_settings` / `set_ui_settings`: read and validate persisted native presentation options.
- `tv_guide.get_programmes`: response-only cached programme query, with offset-aware `start`/`end`, optional `channel_id` and `limit` (1–500). Maximum range: seven days. Returns `programmes`, `count` and `truncated`; each record includes a stable native `id`.
- `tv_guide.get_channels`: response-only catalogue including availability and saved sender order/selection.
- `tv_guide.set_channels`: persist an ordered list in `channels`; `[]` means all.
- `tv_guide.get_saved_programmes`: response-only `bookmarks` and `reminders`, filtering expired records without writing storage. Also available with no EPG source.
- `tv_guide.save_bookmark` / `tv_guide.save_reminder`: accept `id`, `title`, `channel`, `channel_id`, offset-aware ISO `start` and `end`; reminders also accept `minutes`.
- `tv_guide.remove_saved_programme`: accepts `id` and `kind` (`bookmark`, `reminder`, or `programme` to remove both atomically).

These actions currently require exactly one loaded entry/feed as applicable. A storage failure rolls back the saved-list action's in-memory changes. Reminder delivery failures remain pending and retry within the existing bounded delivery window; sent reminders are not rearmed on restart. Notification delivery itself still needs testing in a running Home Assistant.

## Optional add-on state bridge

To test the five bridge entities, keep the add-on running and enable its optional sensors under **Settings → Advanced → Available sensors**. The integration listens to these states without polling. Missing or disabled source states leave the bridge entities unavailable. Existing automations should continue using their original IDs during migration; native IDs deliberately differ.

Fresh native bookmark/reminder storage is empty. The integration does not read or overwrite add-on files, and the native counts may differ from the add-on counts.

## Validation and remaining work

Local validation for the native-card change: 86 Python offline tests passed; eight Chromium workflow scenarios passed (including pixel comparisons, sender picker, saved-item actions, service errors, RPC source checks and reconnect). Tests use HA doubles; they do not run a real HA server. The suite now loads pure Python helpers without inserting the integration directory into `sys.path`, avoiding accidental shadowing of Python's `calendar` module.

The branch has passed Python/JSON checks, Chromium card tests and Hassfest on GitHub Actions. HACS publication validation still requires repository topics; project branding is bundled under `brand/` using an unchanged copy of the original TV Guide project icon (not broadcaster logos).

GitHub Actions runs offline tests, Python/JSON validation, HACS, Hassfest and Chromium card tests. Check the actual results for the branch/PR; local success does not establish CI success.

Before replacing the add-on, test real HA installation/reload/unload, country feed sizes and availability, mobile-notification delivery, storage failures, and card setup on desktop/mobile. Provider fallback/enrichment, multi-country personal lists, programme artwork and explicit old-data migration remain required. See [architecture](docs/ARCHITECTURE.md) and [manual test steps](docs/NATIVE_CARD_TESTING.md).

## Licence

MIT covers project-authored source code. External programme data, logos and broadcaster marks are not covered by it; consult the add-on's third-party notices. The native card bundles the original main-channel logo subset with the inherited notices and Source Sans Pro font licence; third-party assets remain outside the project source-code licence.
