# TV Guide installation and acceptance checklist

Install the complete `custom_components/tv_guide` directory under `/config/custom_components/tv_guide`, restart Home Assistant, and add **TV Guide** under **Settings → Devices & services**. The initial configuration uses Home Assistant's country and language. The complete guide appears automatically as **TV Guide** in the sidebar. No dashboard setup is required to use it.

1. Verify that setup completes and six entities appear: four sensors, one EPG refresh binary sensor, and one programme calendar. Verify the entity names follow the HA profile language.
2. Open **TV Guide** from the sidebar without configuring a dashboard. For the optional dashboard-card test, select **TV Guide** in Home Assistant’s visual card picker. Check Now, 18:00, 20:15, 22:00 and date/time switching, desktop/mobile layouts, and light/dark themes.
3. Check programme details (title, subtitle, description, category, artwork, start/end). First programme downloads may take several minutes.
4. Select, reorder, save and restore channels. Verify switching countries does not show stale programme data for the previous country.
5. Save and remove bookmarks and future reminders. Check counts, next-reminder sensor, persistence and notification delivery to a configured HA notification service.
6. Verify that a reload or HA restart preserves settings and saved programmes; that removing the integration deletes its six registered entities and its entry-owned storage; and that unrelated entities remain untouched.
7. Confirm background EPG downloads and active-country cache maintenance do not duplicate workers or run after unload. An idle maintenance check does not itself imply a provider request.
8. For the optional dashboard card, verify the selected Home Assistant theme in the visual card editor and that card settings survive editing.
9. Test Home Assistant actions `tv_guide.get_guide`, `tv_guide.get_personal_channels`, `tv_guide.get_programmes` and `calendar.get_events` with valid input.
10. Verify broadcaster and local-logo availability for the selected countries and check Home Assistant logs for provider failures.

The automated tests use fixture programmes and a Home Assistant runtime. They do not establish provider availability, real notification delivery, or Raspberry Pi CPU and memory consumption under live conditions. Those require a practical installation test.
