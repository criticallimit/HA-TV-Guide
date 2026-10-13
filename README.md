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

During setup, select one of the ten country baselines, supply a custom XMLTV URL, or leave both blank to use only the add-on bridge. A custom URL overrides the selected country baseline. To test a standalone feed, enter a public HTTPS XMLTV address. The coordinator fetches and parses the configured source, normally every three hours, and creates **TV Guide EPG programmes** to report the programme count.

This standalone source is independent of the add-on but does **not** yet reproduce TV Guide's country-specific provider fallback, local logos, bookmarks, reminders, or complete UI. The native bridge's other five sensors still depend on the add-on.

Only use feeds you are authorized to access. The network restrictions and XML parser are experimental and need live integration testing before production use. The first download happens during setup. If this fetch fails, Home Assistant reports the entry as not ready and retries rather than silently pretending the EPG is available.

## Native programme calendar (experimental)

An optional XMLTV feed now creates **TV Guide Programmes** as a read-only Home Assistant calendar. Each programme becomes a calendar event with start and end, title, description and channel ID (as event location). Open the Home Assistant calendar interface or call `calendar.get_events` to inspect them. The calendar combines all channels into one timeline; overlapping broadcasts are expected. A per-channel programme grid, country source selection, programme artwork and notifications are **not yet implemented**.

The calendar is only created when a standalone feed URL is configured. The XMLTV source must supply timezone-aware timestamps. Existing add-on operation and its reminder system are unchanged.

## Country baselines (experimental)

The setup and options forms now offer DE, AT, CH, NL, BE, DK, NO, FR, SE and GB, mapped to the baseline Open-EPG feed identifiers used by the existing add-on. These country selections are **not** the complete source system: official broadcaster enrichment, alternative provider fallbacks, the original per-country channel catalogues and user-curated sender ordering are not yet migrated. No feed availability or redistribution rights are implied. The current 8 MiB decompressed data limit may reject large country files; this requires real feed tests before production use.

## XMLTV channel catalogue groundwork

The EPG coordinator now extracts each channel's stable XMLTV ID and human-readable display name from the **same downloaded feed**, with no additional network request. The channel metadata is retained in the coordinator and covered by offline unit tests. It is **not yet exposed as a channel-selection UI**, and the official country catalogues, logo assets, user-defined ordering and provider fallbacks still need migration.

## Experimental personal channel selection

Setup and **Configure** now support a comma-separated list of XMLTV channel IDs (up to 200, preserved in the entered order). Leave the field blank to show all feed channels. The native programme calendar displays events for only the selected IDs; the feed is still downloaded once in full, so this does not create additional requests. Selection is stored in the Home Assistant config entry options, and survives restarts and normal updates.

This is an interim technical field, **not** yet the graphical My Channels editor from the TV Guide add-on. Enter exactly the IDs supplied by your XMLTV feed. Channel names are parsed from the same feed but are not yet exposed as an interactive picker, and calendar events remain chronological rather than grouped in a television grid.

## Original channel catalogues imported

The original ordered main-channel JSON catalogues for all 10 countries are now bundled directly in the integration under `custom_components/tv_guide/catalogs/`. `catalogs.py` loads them without network access and maps feed XMLTV IDs to canonical channel IDs. If a main channel has no matching feed ID, it stays in the catalogue marked unavailable rather than disappearing. The new native **TV Guide EPG channels** sensor reports the count of matched main channels (or raw feed channels without a selected country) and lists unmatched canonical IDs in attributes. Offline tests cover the bundled catalogues and a German alias mapping.

**Limitations:** EPG provider enrichment and all programme UI/personal list/bookmark/reminder workflows are not yet migrated. No compatibility or CI success has been established with a running Home Assistant.
