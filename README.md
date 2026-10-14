# TV Guide – Native Home Assistant Integration

Development package 0.3.1 for a first Home Assistant test. The original `criticallimit/TV-Guide` add-on stays unchanged. This integration hosts its programme engine, country catalogues and original card UI inside Home Assistant.

## Install and test

1. Copy the entire `custom_components/tv_guide` directory to `/config/custom_components/tv_guide` and restart Home Assistant.
2. Add **TV Guide** under Settings → Devices & services. Choose a country; **leave the custom feed URL empty**. This selects the original multi-provider engine. Existing preview entries can switch by opening Configure and submitting with an empty feed URL.
3. Add `/tv_guide/frontend/tv-guide-native-card.js?v=3` as a JavaScript module in dashboard resources.
4. Add a dashboard card:

```yaml
type: custom:tv-guide-native-card
height: 1000
```

The integration starts with its cached country data or an empty catalogue. Programme downloads/enrichment continue in the background; the card reports refresh progress. Initial provider loading may take several minutes, as with the add-on. The card updates cached snapshots automatically. A custom HTTPS feed URL selects the older standalone XMLTV mode instead.

## Original functions now included

- All ten country definitions, original sender catalogues and their XMLTV sources.
- Original official/public/secondary programme adapters, source priorities, timeline validation, merging and retained cache data.
- Native-owned country caches and immediate cache restoration after restart.
- Original main and personal sender views, all-country picker, mixed-country selection, ordering and reset.
- Original programme descriptions, subtitles, categories and artwork URLs.
- Original settings, language, theme, columns, refresh interval and time/date selection.
- Original card appearance, fonts and main-channel logos.
- Native saved programmes, reminders, test notifications and HA notification targets.
- Registry-backed count/status entities and a programme calendar; existing add-on entity IDs remain separate.

Programme/source logic is copied from reference commit `7871c4af8951c1f05ed012d028786181b1974b11`; adaptation/provenance are recorded in `original_backend/REFERENCE.json`. The copied backend does not start an HTTP server, bind ports or call Supervisor. Blocking provider/cache work runs outside the HA event loop in an entry-owned worker pool. Reload/unload waits for active workers. Data lives below `/config/.storage/tv_guide_native/<entry_id>`; bookmarks/reminders use HA Store separately. Old add-on files are never read or changed.

The original engine's download/cache policies apply in default mode, including its 100 MiB wire limit and redirects required by providers. The separate custom-feed mode retains its strict HTTPS/public-DNS policy, 12 MiB wire/8 MiB decoded limits and bounded responses. The default engine returns full original timelines so date selection and artwork work as in the add-on.

## Native actions

`tv_guide.native_request` provides whitelisted original guide/settings/personal-channel/status operations over HA's authenticated service connection. Native `get_native_guide`, `get_native_channels`, `get_ui_settings`, `get_programmes`, `get_channels`, `get_saved_programmes`, `save_bookmark`, `save_reminder` and `remove_saved_programme` remain available. The dashboard uses native save/notification actions and the event-driven HA reminder scheduler.

## Validation and first-test boundaries

127 offline Python tests include inherited public-schedule, programme-title and UK regressions. Nine Chromium workflows cover original pixel comparisons and the full-engine route. CI additionally runs Hassfest and a real Home Assistant container smoke test for setup, native actions, platforms, reload and unload. Provider downloads are replaced by fixture data in that smoke test; check the latest CI result before treating it as passed.

Live backend checks on 14 October 2026 successfully merged DE (71,995 programmes, all 50 main stations) and GB (68,398 programmes, all 20 main stations). These checks ran the native-owned engine outside HA; the real HA smoke remains fixture-backed. Some optional German teletext pages failed local TLS certificate checks, while the other sources supplied complete main-station coverage. A live installation test is still needed; use [the test checklist](docs/NATIVE_CARD_TESTING.md). Additional station logo assets outside the bundled main set currently use text-logo fallback. Legacy sensor switches are disabled because native entities are managed in HA's entity registry. Old saved data requires an explicit migration; it is not imported automatically. Power loss before durable sent-state storage can still cause a reminder to be delivered again after restart. HACS publication validation currently fails for missing repository topics and manifest reads while the repository is private; manual installation is available.

## Licence

MIT covers project-authored source. Programme data, logos and broadcaster marks retain their third-party rights. Inherited notices and the Source Sans Pro font licence are included.
