# Native card manual test checklist

Use a test Home Assistant installation with a backup. Keep the original add-on and its files unchanged.

1. Install the integration folder, restart HA, configure a permitted small HTTPS XMLTV feed and confirm the integration loads. Record HA version, source, programme count and setup outcome.
2. Install the separate native JS resource following README. Add `custom:tv-guide-native-card` while retaining the old card. Confirm no Supervisor/Ingress request is made by the native card.
3. Confirm programme labels and times against the native calendar, including Home Assistant's time zone. Move the window, use the original time tabs and Other times dialogue, and inspect seven rows per sender. Compare colours, fonts, logos and spacing with the original card at the same viewport and theme.
4. Save a bookmark, refresh and verify it in the native bookmark list and count sensor. Remove it, refresh and confirm removal. Restart HA and confirm remaining saved records persist.
5. Add reminders at each supported offset. Confirm sent status, native next-reminder sensor and exactly one notification on successful delivery. Restart before and after delivery. Repeat with a real configured `notify.*` target and test a unavailable target/retry window.
6. In ☰ Sender, deselect, reorder and save. Reopen Configure and verify stored order. Confirm sender-only changes do not trigger a new EPG fetch. Check a canonical channel without a matching feed stays visible but yields no programmes. Reset Standardsortierung.
7. Configure bridge-only mode with no source. Saved lists should remain accessible; sender cards should report missing programme data. Keep the original add-on sensors working.
8. Reload/unload/re-enable the integration. Verify actions and timers do not duplicate; remove/reinsert the card and reconnect the browser. Test in mobile layout and both German/English HA profiles.
9. Inspect logs and browser console for errors. Exercise a failed download and storage/notification failure in a disposable test environment. Test all intended country feeds for the preview size limits before relying on them.

Automated checks do not substitute for this running-HA verification. No old bookmark/reminder migration or provider fallback is included. The original presentation and main-channel logo subset are included, with fixture-based screenshot parity tests.

Frontend protocol references: [HA custom cards](https://developers.home-assistant.io/docs/frontend/custom-ui/custom-card/) and [WebSocket service responses](https://developers.home-assistant.io/docs/api/websocket/).
