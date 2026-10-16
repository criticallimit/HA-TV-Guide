# TV Guide for Home Assistant

See what is on TV now, plan your evening, save programmes and get reminders. TV Guide works on desktop and mobile, with light and dark themes that can follow Home Assistant.

[Dansk](https://criticallimit.github.io/HA-TV-Guide/manuals/da.html) · [Deutsch](https://criticallimit.github.io/HA-TV-Guide/manuals/de.html) · [English](https://criticallimit.github.io/HA-TV-Guide/manuals/en.html) · [Polski](https://criticallimit.github.io/HA-TV-Guide/manuals/pl.html) · [Español](https://criticallimit.github.io/HA-TV-Guide/manuals/es.html) · [Nederlands](https://criticallimit.github.io/HA-TV-Guide/manuals/nl.html) · [Français](https://criticallimit.github.io/HA-TV-Guide/manuals/fr.html) · [Italiano](https://criticallimit.github.io/HA-TV-Guide/manuals/it.html) · [Norsk](https://criticallimit.github.io/HA-TV-Guide/manuals/nb.html) · [Svenska](https://criticallimit.github.io/HA-TV-Guide/manuals/sv.html)

## Available countries

<strong><img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/at.svg" width="20" height="14" alt="Austria flag"> Austria · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/be.svg" width="20" height="14" alt="Belgium flag"> Belgium · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/dk.svg" width="20" height="14" alt="Denmark flag"> Denmark · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/fr.svg" width="20" height="14" alt="France flag"> France · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/de.svg" width="20" height="14" alt="Germany flag"> Germany · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/it.svg" width="20" height="14" alt="Italy flag"> Italy · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/nl.svg" width="20" height="14" alt="Netherlands flag"> Netherlands · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/no.svg" width="20" height="14" alt="Norway flag"> Norway · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/pl.svg" width="20" height="14" alt="Poland flag"> Poland · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/es.svg" width="20" height="14" alt="Spain flag"> Spain · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/se.svg" width="20" height="14" alt="Sweden flag"> Sweden · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/ch.svg" width="20" height="14" alt="Switzerland flag"> Switzerland · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/gb.svg" width="20" height="14" alt="United Kingdom flag"> United Kingdom</strong>

All thirteen countries have prepared main-channel lists, individual channel selections and downloaded channel logos for light and dark themes. Switzerland includes its three language regions; Belgium includes Dutch- and French-language channels. Schedule availability depends on the channel and public source.

Italy includes 45 prepared main channels in a familiar programme-guide order, plus additional national, regional and subscription channels when EPG data is available. Logos support light and dark themes.

Spain includes 48 prepared national and regional main channels, plus additional channels from the available feeds. Its interface and Home Assistant entities are available in Spanish.

Poland includes 50 prepared main channels, additional regional and subscription channels from the available feeds, and a Polish interface with translated Home Assistant entities.

**More countries are planned.** New countries will be added when reliable, publicly available programme data can be supported.

## What you can do

- Choose **Austria, Belgium, Denmark, France, Germany, Italy, the Netherlands, Norway, Spain, Sweden, Switzerland or the United Kingdom**. Each country has prepared main channels and additional channels when schedule data is available.
- Open **Now**, **18:00**, **20:15**, **22:00**, or choose another day and time.
- Create **My channels** with your own selection and order. Combine channels from all supported countries in one personal list. Your selection stays when you change country.
- Open a programme for details, save it and set a reminder 5, 10, 15 or 30 minutes before it starts.
- Use four Home Assistant sensors, one binary sensor and a programme calendar for automations.
- Use **Danish, German, English, Spanish, Dutch, French, Italian, Norwegian or Swedish**. The automatic setting follows your Home Assistant profile.

## Install

TV Guide is a **Home Assistant custom integration** and runs directly in Home Assistant. After adding the integration, its programme view is prepared automatically.

### Install with HACS

Requires Home Assistant **2026.10.1 or newer**, the minimum version verified by this project.

1. [Open TV Guide in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=criticallimit&repository=HA-TV-Guide&category=integration). Until the repository is included in the default HACS catalogue, add `https://github.com/criticallimit/HA-TV-Guide` under **HACS → Custom repositories**, category **Integration**.
2. Download **TV Guide** and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → TV Guide**.
4. Open **TV Guide** in the sidebar. Country, language, programme data, logos and Home Assistant entities are prepared automatically. No feed URL, YAML, dashboard card or resource setup is required.

If TV Guide is already installed manually, let HACS manage the same integration directory and keep your existing TV Guide entry. Do not remove and recreate the integration.

### Manual installation

1. [Download the current integration](https://github.com/criticallimit/HA-TV-Guide/archive/refs/heads/main.zip).
2. Extract the archive and copy `custom_components/tv_guide` to `/config/custom_components/tv_guide` on your Home Assistant installation.
3. Restart Home Assistant, then open **Settings → Devices & services → Add integration → TV Guide**.
4. The integration automatically uses your configured Home Assistant country and language at first setup. The **TV Guide** sidebar entry appears automatically. Open it to use the guide.

The initial EPG download may take a few minutes. Subsequent views use bounded caches, and unmodified guide data is not transferred again.


## Country and language

Open the **settings button** and select **Country & language**. Select the country whose TV schedules you want to see. Switzerland includes channels from its three language regions; Belgium includes Dutch- and French-language channels.

**Automatic · Home Assistant** follows the Home Assistant language settings. If no language is available, Denmark uses Danish, Germany and Austria use German, the Netherlands uses Dutch and Norway uses Norwegian, France uses French, Sweden uses Swedish, Italy uses Italian, Spain uses Spanish, Poland uses Polish and the United Kingdom uses English. For multilingual countries, the browser language is used; English is the fallback. You can also choose a language manually.

Country and language are independent: Swiss schedules can be displayed with a French or English interface. Programme titles and descriptions stay in the source language. A reminder keeps the language used when you created it.

## Personalize the guide

**Main channels** shows the prepared list for your TV country. Open **☰ Channels**, tick the countries you want to browse and search for a channel. Add channels to **My channels** and drag them or use the arrows to set their order. Unticking a country only hides its available channels; it keeps your selected channels. Remove a channel with **×**, then save. **Reset order** restores the main channels of the currently selected TV country. Your previous selection is carried over when you first save the new list.

Settings are grouped into **Country & language**, **Display** and **Reminders**. Set the default view, appearance and channels per row under **Display**. A channel limit of **0** shows the entire selected list. Open **Advanced** to adjust the schedule refresh interval. Sensors are created by Home Assistant automatically. Press **Save** to apply your changes.

## Save programmes and get reminders

Open a programme and select **Save**. Find saved programmes under **★ Saved**. For a saved future programme, enable **Remind me** and choose how early to be notified.

In settings, open **Reminders** and choose Home Assistant or a connected mobile device. Use **Test notification** to check the destination. TV Guide and Home Assistant must be running when the reminder is due.

Your saved programmes and channel lists are available on devices using the same Home Assistant installation and survive restarts and updates.

## Ready to use

After adding the integration, open **TV Guide** in the Home Assistant sidebar. The complete programme view is available there automatically. Home Assistant supplies the initial country and language; TV Guide loads programme data and the logo library in the background. The first opening shows preparation progress while downloads are running. All main-channel and additional-channel artwork comes from this separately downloaded database; the integration package contains matching metadata, but no channel image files. Logo versions are checked in the background once every 24 hours. Unchanged versions need only a small conditional request; new versions download only changed packages. Verified updates appear automatically without restarting Home Assistant, while failed updates keep the installed logos available.

The guide needs no dashboard card, YAML configuration or resource setup. You can start using it directly from the sidebar.

For an optional view in your own dashboard, **TV Guide** is also available in Home Assistant's visual card picker. This is an additional display option; the sidebar already provides the complete guide.

## When something is missing

**No programme for a channel:** Availability depends on public sources. Confirmed broadcaster data is preferred; other feeds fill gaps. Coverage and updates vary by channel and date. Additional schedules now cover Denmark through DR/TV 2, selected Austrian channels through Joyn Austria, and La Une/Tipik/La Trois through RTBF. Dutch RTL/SBS channels also have a TVgids.nl fallback. See [country source notes](https://github.com/criticallimit/HA-TV-Guide/blob/main/custom_components/tv_guide/country_sources.py) for coverage and limitations.

**Empty guide after an update or country change:** Let the download finish and reopen the guide after a few minutes.

**No reminder:** Check the destination in settings and send a test notification. Mobile reminders need a device connected to the Home Assistant app.

## Home Assistant entities

The integration creates Home Assistant registry entities (managed by Home Assistant): last EPG update, saved programme count, reminder count, next reminder, update-running binary sensor and programme calendar. Names are translated into supported Home Assistant languages. Entities are linked to the integration and removed when it is deleted. Their identifiers depend on the Home Assistant entity registry and may vary if customized.


## Updates and help

For a HACS installation, install updates through **HACS** and restart Home Assistant when prompted. For a manual installation, copy the latest `custom_components/tv_guide` directory over the installed integration and restart Home Assistant. Keep the existing integration entry; settings and saved programmes remain in Home Assistant storage.

[Report an issue](https://github.com/criticallimit/HA-TV-Guide/issues) with the country, channel, date and time.


## Legal and third-party content

TV Guide is an independent open-source project. The project-authored code is licensed under the MIT License. Television channel names, trademarks, logos, programme data, programme descriptions and other third-party material are **not** relicensed under MIT and remain subject to the rights and terms of their respective owners and providers.

See [third-party notices](https://github.com/criticallimit/HA-TV-Guide/blob/main/THIRD_PARTY_NOTICES.md) for source, trademark and third-party rights information.


## Adding a country

Register the country once in `custom_components/tv_guide/countries.json` and add its channel catalogue under `catalogs/`. Each registration needs a display name, an IANA timezone, the catalogue filename and an ordered list of working XMLTV source URLs. The first source is primary; subsequent sources are fallbacks. Catalogue channels need stable IDs, names, order and matching XMLTV IDs or aliases. Use country-prefixed IDs for new curated stations.

Setup, settings, the country picker, feed selection, personal lists and caches all use this registration. Optional `language` provides an initial locale fallback; the Home Assistant profile and explicit language selection take precedence. Omit it for multilingual countries. Existing `providers`, `secondary_providers`, `secondary_urls` and `teletext_providers` register optional broadcaster sources through shared adapters. A broadcaster using a new API format needs an adapter; a new country using existing XMLTV feeds does not need a country-specific code path. Logos are optional; provide curated artwork or matching logo-library metadata for full visual coverage.

`storage_prefix` and `source_id_prefix` are compatibility metadata for existing installations; omit both for new countries. Do not change them or existing channel IDs after publishing. Run the Python suite and browser/HA CI before publishing a new country; source availability and schedule quality still depend on the upstream provider.

## Native runtime architecture

Each config entry owns one `ProgrammeEngine`, `SettingsState`, `ProgrammeRepository` and bounded work scheduler. Domain operations are direct method calls; the integration does not create an internal HTTP server or dynamically execute a module per entry. Home Assistant config-entry options own native settings persistence. The runtime keeps a synchronized in-memory snapshot, and restores its previous settings if HA rejects a commit. Standalone engine regressions retain atomic file persistence through the same settings adapter.

Source adapters keep their verified parsing, source priorities and country registrations. Two prioritized network workers serve the currently selected country before queued background work. A separate single worker restores local programme caches, so blocked downloads cannot delay cached content. Native provider requests stream through Home Assistant's pooled HTTP session with bounded buffering. Obsolete country requests are cancelled while waiting for headers or body data. A bounded conditional cache reuses complete responses on HTTP 304; unsupported validators fall back to ordinary downloads.

Programme projections and stable IDs are prepared once per source revision and reused by both channel views. The card requests compact responses that transfer a shared sender timeline once, then uses the complete timelines locally for time navigation. Existing response consumers can continue requesting the original full shape. Presentation and logo changes invalidate their views without rebuilding the HA programme snapshot. Entry unload drains or cancels every owned request and worker while leaving HA's shared HTTP session open.

Immutable logo matching metadata is read directly from the packaged archive; it is not extracted into each entry's storage directory. Startup removes the obsolete `reference/` copy and, for HA-managed entries, the superseded `options.json` mirror. User channel selections, ordering, bookmarks, downloaded logos and valid current programme caches are retained. Programme caches accept only the current schema; older derived snapshots and their catalogue indexes are discarded when opened and rebuilt in the background instead of running historical record migrations. No additional database or HA recorder migration is required.

## Adding a language

`languages.json` is the shared registry for card settings, Home Assistant defaults, settings validation and reminder actions. Add a canonical lowercase language code with its native `name` and optional lowercase `aliases`. Regional profiles resolve from the most specific registered code to the base language, then English; for example `fr_CA` uses `fr`, and the registered `no` alias uses `nb`.

Copy `locales/en.json` to `locales/<code>.json` and translate the values in `messages` and `home_assistant`. Preserve the message keys and `{placeholders}`. This single source supplies the card, reminder notifications, Home Assistant entity names and setup texts. Programme titles remain in the source language. Do not edit generated `frontend/app/translations.js`, `strings.json` or `translations/*.json` directly.

Run:

```sh
python tools/validate_registrations.py
python tools/build_locales.py
python tools/build_frontend_view.py --check
python -m unittest discover -s tests -v
```

CI rejects missing translations, changed placeholders, duplicate registrations, invalid country time zones, invalid source URLs, duplicate sender IDs/order values, unknown logo references and stale generated output. English fallback also protects the running card and reminders when a text is unavailable. Labels wrap within the existing responsive settings layout; verify especially long labels in browser checks.

New countries using an existing source format require only a `countries.json` entry and a sender catalogue in `catalogs/`. Register an optional default `language` only when it is appropriate for the country; a user's explicit choice and HA profile take precedence. Keep published sender IDs stable. Logos may be omitted, but provided database logo references must exist in the indexed logo library. A genuinely new source format still needs a parser adapter.

The real Home Assistant acceptance suite iterates all registered countries and languages. Browser tests iterate every registered language and exercise an injected additional language, regional resolution and English fallback. An isolated integration test adds both a country and language through data files and verifies saving, personal selection, restart and reminder translation without changing runtime code.

Before offline tests, run `python tests/prepare_logo_fixtures.py` to cache verified database samples. The central logo-data publishing and compatibility checks are documented in [Logo database maintenance](docs/LOGO_DATA.md).
