# TV Guide 0.5.5

Native Home Assistant integration with automatic sidebar setup, a visual dashboard card with theme selection, ten TV countries, nine interface languages, personal channels, saved programmes, reminders, sensors and a programme calendar.

## Installation

Home Assistant 2026.10.1 or newer is required.

1. [Open TV Guide in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=criticallimit&repository=HA-TV-Guide&category=integration). Until catalogue inclusion, add the repository as category **Integration**.
2. Download TV Guide and restart Home Assistant.
3. Add **TV Guide** under **Settings → Devices & services → Add integration**.
4. Open **TV Guide** in the sidebar. Country and language are adopted automatically; first downloads show preparation progress.

No manual feed URL, dashboard resource or YAML configuration is required. Existing users should update through HACS and restart, keeping their existing TV Guide entry.

## Verification

Version 0.5.5 passed 238 Python tests, 21 browser test groups with reference screenshots, Hassfest, and acceptance tests in an isolated real Home Assistant 2026.10.1 instance. The HA test exercises authenticated HTTP/WebSocket, all ten countries, reminders, stored data, reload and removal. Programme provider downloads in that acceptance test use fixed test data.

HACS packaging metadata and validation are included. The logo library downloads from this integration's own pinned GitHub data; no installed add-on is required.

[User manuals](https://criticallimit.github.io/HA-TV-Guide/) · [Third-party notices](https://github.com/criticallimit/HA-TV-Guide/blob/main/THIRD_PARTY_NOTICES.md)
