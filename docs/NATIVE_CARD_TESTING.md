# First Home Assistant test

Install the complete `custom_components/tv_guide` directory, restart HA and add TV Guide. The entry is created immediately without a form, using HA country/language. Open TV Guide in the sidebar; the panel and native card module are registered automatically. Existing previews with no explicit custom URL migrate automatically. Run the installation without an add-on. The development checkout is the visual reference only.

1. Confirm the integration loads immediately, creates native sensors/calendar and reports background refresh. Allow several minutes for the original provider adapters to finish. Inspect Settings → System → Logs if programme data stays empty.
2. Compare main cards, now/18:00/20:15/22:00, another date/time, desktop/mobile and light/dark with the development reference using the same country/time. Rotate a mobile device into landscape; the sidebar guide must fit the available height. Provider data can change between downloads.
3. Open a programme with available artwork. Check title, episode/subtitle, description, category, image and real start/end times.
4. Open Sender. Select channels from DE and AT (or another pair), reorder and save. Reopen the picker, inspect the personal view and wait for the selected country caches to load. Reset the list.
5. Change country, language, columns and default time in card settings; confirm they survive integration reload and HA restart.
6. Save/remove a bookmark and future reminder. Check native counts, next reminder and persistence after restart. Choose a real mobile notification target, send a test and check actual delivery at the selected reminder offset.
7. Reload, unload and enable the integration while a source is loading. Running provider requests are drained before unload completes; source timeouts can delay this. Confirm services/workers/timers do not duplicate.
8. Confirm setup works with no installed add-on. Existing unrelated entities must neither be read as native data nor modified.

The real-HA CI smoke uses the official stable HA image and fixture provider data. Offline/browser tests verify adapters and presentation; live provider availability and notification targets must be checked on your installation. The complete logo library is packaged; bookmarks and reminders use only native saved data. Check that the settings dialogue omits manual dashboard setup and sensor switches, while the sidebar, card module and native entities are provided automatically.

9. Check inactive-country cache warming after two-minute idle intervals; active downloads take priority. Sent reminders must stop contributing to the pending count, and switching to an uncached country must clear the previous last-update timestamp. Native mode should create no add-on bridge entities.

10. Select an additional channel with a matching library asset. Both logo themes should load through /tv_guide/logo/ without any external image request. Unknown logo paths must return 404. Native bookmark counts must ignore stale browser caches and unrelated similarly named entities.

11. Leave the guide closed beyond its configured refresh interval and confirm active data refreshes through the maintenance timer. Request a forced refresh while normal work is running; it must not be lost. Check calendar channel selection and overlapping time ranges with a large cached programme set.

12. Choose an installed HA theme in the Lovelace visual card editor. Test light/dark theme mode values, then reset to Home Assistant / Dashboard. The card height and other YAML settings must survive the selection.

13. Call get_native_guide with an aware at timestamp, get_programmes with a time range and calendar.get_events with start_date_time/end_date_time. Test the save_reminder minute selector in HA Developer Tools. A country-qualified sender ID longer than 120 characters must survive native storage and reload.
