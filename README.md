# TV Guide for Home Assistant

See what is on TV now, plan your evening, save programmes and get reminders. TV Guide works on desktop and mobile, with light and dark themes that can follow Home Assistant.

[Dansk](https://criticallimit.github.io/HA-TV-Guide/manuals/da.html) · [Deutsch](https://criticallimit.github.io/HA-TV-Guide/manuals/de.html) · [English](https://criticallimit.github.io/HA-TV-Guide/manuals/en.html) · [Español](https://criticallimit.github.io/HA-TV-Guide/manuals/es.html) · [Nederlands](https://criticallimit.github.io/HA-TV-Guide/manuals/nl.html) · [Français](https://criticallimit.github.io/HA-TV-Guide/manuals/fr.html) · [Italiano](https://criticallimit.github.io/HA-TV-Guide/manuals/it.html) · [Norsk](https://criticallimit.github.io/HA-TV-Guide/manuals/nb.html) · [Svenska](https://criticallimit.github.io/HA-TV-Guide/manuals/sv.html)

## Available countries

<strong><img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/at.svg" width="20" height="14" alt="Austria flag"> Austria · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/be.svg" width="20" height="14" alt="Belgium flag"> Belgium · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/dk.svg" width="20" height="14" alt="Denmark flag"> Denmark · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/fr.svg" width="20" height="14" alt="France flag"> France · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/de.svg" width="20" height="14" alt="Germany flag"> Germany · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/nl.svg" width="20" height="14" alt="Netherlands flag"> Netherlands · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/no.svg" width="20" height="14" alt="Norway flag"> Norway · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/se.svg" width="20" height="14" alt="Sweden flag"> Sweden · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/ch.svg" width="20" height="14" alt="Switzerland flag"> Switzerland · <img src="https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/docs/flags/gb.svg" width="20" height="14" alt="United Kingdom flag"> United Kingdom</strong>

All ten countries have prepared main-channel lists, individual channel selections and local channel logos for light and dark themes. Switzerland includes its three language regions; Belgium includes Dutch- and French-language channels. Schedule availability depends on the channel and public source.

**More countries are planned.** New countries will be added when reliable, publicly available programme data can be supported.

## What you can do

- Choose **Austria, Belgium, Denmark, France, Germany, the Netherlands, Norway, Sweden, Switzerland or the United Kingdom**. Each country has prepared main channels and additional channels when schedule data is available.
- Open **Now**, **18:00**, **20:15**, **22:00**, or choose another day and time.
- Create **My channels** with your own selection and order. Combine channels from all supported countries in one personal list. Your selection stays when you change country.
- Open a programme for details, save it and set a reminder 5, 10, 15 or 30 minutes before it starts.
- Use native Home Assistant sensors, a binary sensor and a programme calendar for automations.
- Use **Danish, German, English, Dutch, French, Italian, Norwegian or Swedish**. The automatic setting follows your Home Assistant profile.

## Install — native Home Assistant integration

TV Guide is a **native custom integration**, not a Supervisor add-on. No separate add-on server, HACS or manual Lovelace resource registration is required.

1. [Download the current integration](https://github.com/criticallimit/HA-TV-Guide/archive/refs/heads/main.zip).
2. Extract the archive and copy `custom_components/tv_guide` to `/config/custom_components/tv_guide` on your Home Assistant installation.
3. Restart Home Assistant, then open **Settings → Devices & services → Add integration → TV Guide**.
4. The integration automatically uses your configured Home Assistant country and language at first setup. Open **TV Guide** in the sidebar or add `type: custom:tv-guide-native-card` to a dashboard.

The initial EPG download may take a few minutes. Subsequent views use bounded caches, and unmodified guide data is not transferred again.


## Country and language

Open the **settings button** and select **Country & language**. Select the country whose TV schedules you want to see. Switzerland includes channels from its three language regions; Belgium includes Dutch- and French-language channels.

**Automatic · Home Assistant** follows the Home Assistant language settings. If no language is available, Denmark uses Danish, Germany and Austria use German, the Netherlands uses Dutch and Norway uses Norwegian, France uses French, Sweden uses Swedish and the United Kingdom uses English. For multilingual countries, the browser language is used; English is the fallback. You can also choose a language manually.

Country and language are independent: Swiss schedules can be displayed with a French or English interface. Programme titles and descriptions stay in the source language. A reminder keeps the language used when you created it.

## Personalize the guide

**Main channels** shows the prepared list for your TV country. Open **☰ Channels**, tick the countries you want to browse and search for a channel. Add channels to **My channels** and drag them or use the arrows to set their order. Unticking a country only hides its available channels; it keeps your selected channels. Remove a channel with **×**, then save. **Reset order** restores the main channels of the currently selected TV country. Your previous selection is carried over when you first save the new list.

Settings are grouped into **Country & language**, **Display** and **Reminders**. Set the default view, appearance and channels per row under **Display**. A channel limit of **0** shows the entire selected list. Open **Advanced** to adjust the schedule refresh interval. Native sensors are created by Home Assistant automatically. Press **Save** to apply your changes.

## Save programmes and get reminders

Open a programme and select **Save**. Find saved programmes under **★ Saved**. For a saved future programme, enable **Remind me** and choose how early to be notified.

In settings, open **Reminders** and choose Home Assistant or a connected mobile device. Use **Test notification** to check the destination. TV Guide and Home Assistant must be running when the reminder is due.

Your saved programmes and channel lists are available on devices using the same Home Assistant installation and survive restarts and updates.

## Add the dashboard card

The integration automatically registers its Lovelace module. Add a manual dashboard card with:

```yaml
type: custom:tv-guide-native-card
height: 1000
```

No `/local/tv-guide-card-loader.js` resource, add-on or Ingress configuration is needed.


## When something is missing

**No programme for a channel:** Availability depends on public sources. Confirmed broadcaster data is preferred; other feeds fill gaps. Coverage and updates vary by channel and date. Additional schedules now cover Denmark through DR/TV 2, selected Austrian channels through Joyn Austria, and La Une/Tipik/La Trois through RTBF. Dutch RTL/SBS channels also have a TVgids.nl fallback. See [the original source notes](https://github.com/criticallimit/TV-Guide/blob/main/tv-guide/data/COUNTRY_SOURCES.md) for coverage and limitations.

**Empty guide after an update or country change:** Let the download finish and reopen the guide after a few minutes.

**No reminder:** Check the destination in settings and send a test notification. Mobile reminders need a device connected to the Home Assistant app.

## Native Home Assistant entities

The integration creates native Home Assistant registry entities (rather than add-on REST-published states): EPG programme count, channel count, last update, saved programme count, reminder count, next reminder, update-running binary sensor and programme calendar. Names are translated into supported Home Assistant languages. Entities are linked to the integration and removed when it is deleted. Their identifiers depend on the Home Assistant entity registry and may vary if customized.


## Updates and help

For this development version, update by copying the latest `custom_components/tv_guide` directory over the installed integration and restarting Home Assistant. **There is no published release or add-on store update yet.**

[Report an issue](https://github.com/criticallimit/HA-TV-Guide/issues) with the country, channel, date and time.


## Legal and third-party content

TV Guide is an independent open-source project. The project-authored code is licensed under the MIT License. Television channel names, trademarks, logos, programme data, programme descriptions and other third-party material are **not** relicensed under MIT and remain subject to the rights and terms of their respective owners and providers.

See [original third-party notices](https://github.com/criticallimit/TV-Guide/blob/main/THIRD_PARTY_NOTICES.md) for source, trademark and third-party rights information.

