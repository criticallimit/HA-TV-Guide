# First Home Assistant test

Install the complete `custom_components/tv_guide` directory, restart HA and add TV Guide. The entry is created immediately without a form, using HA country/language. Open TV Guide in the sidebar; the panel and native card module are registered automatically. Existing previews with no explicit custom URL migrate automatically. Keep the add-on available as the comparison reference.

1. Confirm the integration loads immediately, creates native sensors/calendar and reports background refresh. Allow several minutes for the original provider adapters to finish. Inspect Settings → System → Logs if programme data stays empty.
2. Compare main cards, now/18:00/20:15/22:00, another date/time, desktop/mobile and light/dark with the add-on using the same country/time. Provider data can change between downloads.
3. Open a programme with available artwork. Check title, episode/subtitle, description, category, image and real start/end times.
4. Open Sender. Select channels from DE and AT (or another pair), reorder and save. Reopen the picker, inspect the personal view and wait for the selected country caches to load. Reset the list.
5. Change country, language, columns and default time in card settings; confirm they survive integration reload and HA restart.
6. Save/remove a bookmark and future reminder. Check native counts, next reminder and persistence after restart. Choose a real mobile notification target, send a test and check actual delivery at the selected reminder offset.
7. Reload, unload and enable the integration while a source is loading. Running provider requests are drained before unload completes; source timeouts can delay this. Confirm services/workers/timers do not duplicate.
8. Verify the original add-on files, personal settings, saved records and entity IDs remain untouched. Native storage is independent.

The real-HA CI smoke uses the official stable HA image and fixture provider data. Offline/browser tests verify adapters and presentation; live provider availability and notification targets must be checked on your installation. Remaining detail work includes extra-station logo assets and explicit migration of old saved data. Native entities are controlled through HA's entity registry.
