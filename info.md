# TV Guide

TV schedules, personal channel lists, saved programmes and reminders directly in Home Assistant. Includes thirteen TV countries, a multilingual interface, light and dark themes, automatic sensors and a programme calendar.

## Install with HACS

Until TV Guide is included in the default HACS catalogue, [open this repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=criticallimit&repository=HA-TV-Guide&category=integration), or add `https://github.com/criticallimit/HA-TV-Guide` under **HACS → Custom repositories**, category **Integration**.

Download **TV Guide**, restart Home Assistant, then open **Settings → Devices & services → Add integration → TV Guide**. Home Assistant 2026.10.1 or newer is required; this is the minimum version verified by the project.

The integration adopts your Home Assistant country and language and prepares everything automatically. Open **TV Guide** in the sidebar. Initial programme and logo downloads show their progress and may take a few minutes.

No feed URL, YAML, dashboard resource or manual card setup is required. An optional TV Guide card is available in the visual dashboard card picker, including a theme selector.

## Countries

<img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/pl.svg" width="20" height="14" alt="Poland flag"> **Poland is included**, with 50 main channels, additional regional and subscription channels and a Polish interface.

<img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/es.svg" width="20" height="14" alt="Spain flag"> **Spain is now included**, with 48 national and regional main channels, additional available feed channels and a Spanish interface.

<img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/it.svg" width="20" height="14" alt="Italy flag"> **Italy is now included**, with 45 main channels and additional available feed channels.

Austria, Belgium, Denmark, France, Germany, Italy, the Netherlands, Norway, Poland, Spain, Sweden, Switzerland and the United Kingdom. Programme availability depends on the channel and public data source.

## Updates and existing installations

Install updates through HACS and restart Home Assistant when prompted. If you already installed TV Guide manually, let HACS manage the same repository and integration directory. Keep your existing TV Guide integration entry; do not remove and recreate it. Settings and saved programmes are stored separately in Home Assistant storage.

[User manuals](https://criticallimit.github.io/HA-TV-Guide/) · [Report a problem](https://github.com/criticallimit/HA-TV-Guide/issues) · [Third-party notices](https://github.com/criticallimit/HA-TV-Guide/blob/main/THIRD_PARTY_NOTICES.md)
