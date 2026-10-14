# TV Guide – Native Home Assistant Integration

Development package 0.4.6 for a first Home Assistant test. This standalone integration hosts its own programme engine, country catalogues, card UI and complete offline logo library inside Home Assistant. The TV-Guide repository is used only as a read-only development reference; an installed add-on is never consulted.

## Install and test

1. Copy the entire `custom_components/tv_guide` directory to `/config/custom_components/tv_guide` and restart Home Assistant.
2. Add **TV Guide** under Settings → Devices & services. There is no input form: country and language come from Home Assistant, the original provider engine is selected, and background loading starts automatically.
3. Open **TV Guide** in the HA sidebar. The panel and native card module are registered automatically; no feed URL, resource registration or dashboard YAML is needed.

An optional dashboard card can be added using `type: custom:tv-guide-native-card` and `height: 1000`; its JavaScript is already loaded by the integration. Country/language and personal preferences can be changed later in the TV Guide settings. Supported HA countries are used directly; unsupported/missing country settings fall back to the supported country matching the HA language (DE for languages without a matching country). Norwegian locale codes are normalized to `nb`.

The integration starts with cached data or an empty catalogue. Downloads/enrichment continue in the background and can take several minutes. Older previews with no explicit custom URL are upgraded automatically to the original engine using HA locale settings. Previously configured custom URLs remain functional, but URL/technical setup forms are no longer shown.

## Original functions now included

- All ten country definitions, original sender catalogues and their XMLTV sources.
- Original official/public/secondary programme adapters, source priorities, timeline validation, merging and retained cache data.
- Native-owned country caches and immediate cache restoration after restart.
- Original main and personal sender views, all-country picker, mixed-country selection, ordering and reset.
- Original programme descriptions, subtitles, categories and artwork URLs.
- Original settings, language, theme, columns, refresh interval and time/date selection.
- Original card appearance, fonts and all curated main-channel logos.
- Complete offline logo library: 20,292 source images, stored as 18,528 deduplicated objects in 37 native bundles. Europe SVG dependencies are embedded in the response.
- Automatic inactive-country cache preloading through an owned HA timer, with active-country priority.
- Native saved programmes, reminders, test notifications and HA notification targets.
- Registry-backed count/status entities and a programme calendar backed exclusively by this integration.

Programme/source logic is copied from reference commit `7871c4af8951c1f05ed012d028786181b1974b11`; adaptation/provenance are recorded in `original_backend/REFERENCE.json`. The copied backend does not start an HTTP server, bind ports or call Supervisor. Blocking provider/cache work runs outside the HA event loop in an entry-owned worker pool. Reload/unload waits for active workers. Data lives below `/config/.storage/tv_guide_native/<entry_id>`; bookmarks/reminders use HA Store separately. There is no add-on state bridge, browser-bookmark import, Supervisor access or add-on discovery.

The original engine's download/cache policies apply in default mode, including its 100 MiB wire limit and redirects required by providers. The separate custom-feed mode retains its strict HTTPS/public-DNS policy, 12 MiB wire/8 MiB decoded limits and bounded responses. The default engine returns full original timelines so date selection and artwork work as in the add-on.

## Native actions

`tv_guide.native_request` provides whitelisted original guide/settings/personal-channel/status operations over HA's authenticated service connection. Native `get_native_guide`, `get_native_channels`, `get_ui_settings`, `get_programmes`, `get_channels`, `get_saved_programmes`, `save_bookmark`, `save_reminder` and `remove_saved_programme` remain available. The dashboard uses native save/notification actions and the event-driven HA reminder scheduler. Pending-reminder counts omit sent and grace-expired items; timestamp attributes retain the original due time. All state-bridge classes, constants and publishing helpers have been removed.

## Validation and first-test boundaries

189 offline Python tests include inherited public-schedule, programme-title, UK, Norwegian, source-outage, cache-memory and JSON-persistence regressions. Fourteen Chromium workflows cover original pixel comparisons, all ten country views, all eight interface languages, mobile portrait/landscape, the visual HA theme selector and the full-engine route. CI additionally runs Hassfest and a real Home Assistant container smoke test for setup, native actions, platforms, reload and unload. Provider downloads are replaced by fixture data in that smoke test; check the latest CI result before treating it as passed.

Live backend checks on 14 October 2026 successfully merged DE (71,995 programmes, all 50 main stations) and GB (68,398 programmes, all 20 main stations). These checks ran the native-owned engine outside HA; the real HA smoke remains fixture-backed. Some optional German teletext pages failed local TLS certificate checks, while the other sources supplied complete main-station coverage. A live installation test is still needed; use [the test checklist](docs/NATIVE_CARD_TESTING.md). The full shipped logo library is available offline; only stations without a matching source asset use the original text-logo fallback. The sidebar, card module and native sensors are provided automatically. The settings dialogue has no manual dashboard setup or sensor switches. Saved records are native HA Store data only; no import from an installed add-on is offered or planned. Power loss before durable sent-state storage can still cause a reminder to be delivered again after restart. HACS publication validation currently fails for disabled repository issues, missing topics and unavailable manifest reads while the repository is private; manual installation is available.

## Licence

MIT covers project-authored source. Programme data, logos and broadcaster marks retain their third-party rights. Inherited notices and the Source Sans Pro font licence are included.
