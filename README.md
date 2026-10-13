# TV Guide – Native Home Assistant Integration

**Development preview.** This project adds a custom integration named **TV Guide** to Home Assistant. It is separate from the existing [TV Guide add-on](https://github.com/criticallimit/TV-Guide).

> The integration provides a configurable experimental XMLTV downloader and a temporary add-on state bridge. It does **not** yet reproduce the full TV Guide experience. Five native registry-backed entities mirror optional state values published by the existing add-on. Supplying an HTTPS XMLTV URL also enables a separate EPG programme-count sensor. Continue using the existing add-on for television schedules, reminders and the dashboard card.

## Manual test installation (without HACS)

1. Copy the complete `custom_components/tv_guide` directory to `/config/custom_components/tv_guide` on your Home Assistant installation.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration** and search for **TV Guide**.
4. Complete the preliminary setup. No URL or credentials are needed.

### Test the initial native sensors

1. Leave the TV Guide add-on running.
2. In the add-on, enable the five optional sensors under **Settings → Advanced → Available sensors**, and save.
3. The new native integration listens to the existing add-on states without any polling or EPG downloads. It creates four sensors and one binary sensor with names beginning **TV Guide Native**.
4. Inspect the values under **Settings → Devices & services → TV Guide → Entities**.
5. If the add-on sensors are disabled, the new entities remain registered but report **unavailable**.

**Important:** During this bridge phase the old add-on states must remain enabled. Existing automations should continue to use the original IDs. The new entities have separate names and stable unique IDs to avoid collisions. The integration is not yet a standalone TV Guide replacement.

To install future test commits without HACS, copy the updated folder over the old one, back up first, then restart Home Assistant. GitHub does not automatically deploy changes to your installation.

## What is next?

- Replace the experimental single-feed test path with the supported country/source catalogue and reliable provider fallbacks.
- Standalone native Home Assistant sensor and binary sensor data sources (the temporary native bridge is already implemented).
- Safe migration from existing REST-published state-only sensors.
- Expose programme schedules to a Home Assistant-native UI and restore card, saved shows and reminders.
- Verify transport protection, Home Assistant startup/unload, updates, and CI on real instances.
- Automated integration tests and a supported test-installation/update workflow.

See [architecture and migration constraints](docs/ARCHITECTURE.md).

## Change the feed after installation

Open **Settings → Devices & services → TV Guide → Configure**. You may change the XMLTV feed URL or clear it to disable standalone feed downloads. Saving options reloads the integration. The existing five add-on-state mirrors remain available.

## CI

GitHub Actions contains HACS, Hassfest and Python/JSON syntax validation. A passing check verifies only those checks and **does not** imply that the integration has been tested in a running Home Assistant.

## Licence

MIT applies to the project-authored source code. External programme data, channel logos and broadcaster marks are not covered by this licence; see the existing add-on's third-party notices.

## Optional experimental EPG source

During setup, leave the XMLTV URL blank to use only the add-on bridge. To test a standalone feed, enter a public HTTPS XMLTV address. The coordinator fetches and parses this source, normally every three hours, and creates **TV Guide EPG programmes** to report the programme count.

This standalone source is independent of the add-on but does **not** yet reproduce TV Guide's country-specific provider fallback, local logos, bookmarks, reminders, or complete UI. The native bridge's other five sensors still depend on the add-on.

Only use feeds you are authorized to access. The network restrictions and XML parser are experimental and need live integration testing before production use. The first download happens during setup. If this fetch fails, Home Assistant reports the entry as not ready and retries rather than silently pretending the EPG is available.

## Native programme calendar (experimental)

An optional XMLTV feed now creates **TV Guide Programmes** as a read-only Home Assistant calendar. Each programme becomes a calendar event with start and end, title, description and channel ID (as event location). Open the Home Assistant calendar interface or call `calendar.get_events` to inspect them. The calendar combines all channels into one timeline; overlapping broadcasts are expected. A per-channel programme grid, country source selection, programme artwork and notifications are **not yet implemented**.

The calendar is only created when a standalone feed URL is configured. The XMLTV source must supply timezone-aware timestamps. Existing add-on operation and its reminder system are unchanged.
