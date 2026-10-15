# First display of an already populated guide

Version 0.5.2 requests a small first view for both the Lovelace card and sidebar.
The parent starts this authenticated HA request while the iframe loads. The iframe
consumes that one response, paints the seven programme rows per sender, then
requests complete timelines after two animation frames. No provider download is
needed to open an already populated guide.

The first response keeps channel ordering, logos, descriptions, stable programme
IDs, preparation status and the configured default view. Preset times use the
browser's time zone, just like the existing renderer. The complete guide remains
available for time/date navigation and programme details. A partial response never
sends `known_revision`: only complete in-memory timelines can accept an unchanged
reply. Failure of the preview falls back to the ordinary full request.

The tab-local first-paint cache keeps seven rows at the configured default time
instead of 24 rows around the current time. It is limited to 1 MiB of characters,
expires after 60 seconds, and is refreshed from HA on each opening. No additional
provider polling or persistent browser database is introduced.

## Reproducible verification

- Offline runtime test: 336 half-hour programmes per sender, descriptions retained,
  default German sender lists (main and personal views), no provider requests.
  The test asserts more than a 20-fold smaller first response and verifies that
  the full cached timelines remain intact.
- Browser test: explicitly withhold the full response, verify that channel cards
  are visible, only one preview was requested, and no conditional revision was
  sent. Release the response and verify all 80 fixture programmes arrive, a time
  selected during loading remains selected, and later time changes are local.
- Existing browser pixel comparisons retain the original renderer, CSS, fonts,
  logos and toolbar across desktop/mobile, ten countries and eight UI languages.
- HA runtime smoke test exercises the preview through the actual service and
  verifies that subsequent full requests remain complete.

An offline synthetic measurement on the development machine produced 38,914,390
bytes for the full response versus 891,608 bytes for the first view: 97.7% less
initial data. Serialization took approximately 175 ms versus 6 ms. This measures
payload preparation/serialization, not the user's HA rendering time or network.
Complete timelines still transfer in the background. The installed system must
be compared after updating and restarting Home Assistant.
