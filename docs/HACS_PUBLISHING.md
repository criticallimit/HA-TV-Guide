# HACS-Veröffentlichung vorbereiten und abschließen

Stand: 15. Oktober 2026. Repository: `criticallimit/HA-TV-Guide`, Kategorie **Integration**, Domain `tv_guide`, Version `1.0.0`.

## Bereits vorbereitet

- `hacs.json` mit Name, allen zehn unterstützten TV-Ländern und Home Assistant `2026.10.1` als tatsächlich geprüfter Mindestversion.
- `info.md` als HACS-Beschreibung mit Installation, automatischer Einrichtung und Updates; HACS verwendet diese Datei statt des README.
- `.github/workflows/hacs.yml`: offizielle HACS-Prüfung bei Änderungen, veröffentlichten Releases, wöchentlich und manuell. Keine Prüfungen werden ignoriert. Die Action schreibt keine PR-Kommentare.
- Vorhandene Hassfest-, Python-, Browser- und echte Home-Assistant-Prüfungen bleiben aktiv.
- Eigenes Icon unter `custom_components/tv_guide/brand/icon.png`. Der aktuelle HACS-Validator akzeptiert dieses lokale Branding; ein zusätzlicher Antrag bei `home-assistant/brands` ist dafür nicht erforderlich.
- Versionskennung `1.0.0` im Integrationsmanifest; das GitHub-Release verwendet den Tag `v1.0.0`.

HACS lädt den vollständigen Ordner `custom_components/tv_guide` aus dem gewählten Git-Stand. `zip_release` wird bewusst nicht verwendet: Es ist kein besonderes Release-ZIP nötig. Die automatisch von GitHub angebotenen Quellarchive reichen aus. Programm- und Logo-Daten bleiben in der eigenen HA-Speicherung außerhalb des von HACS ersetzten Integrationsordners.

## 1. Repository-Einstellungen vervollständigen

1. Auf [Settings → General](https://github.com/criticallimit/HA-TV-Guide/settings) unter **Features** die Option **Issues** aktivieren.
2. Auf der [Repository-Startseite](https://github.com/criticallimit/HA-TV-Guide) rechts bei **About** über das Zahnrad mindestens die Topics `home-assistant`, `hacs` und `tv-guide` eintragen.
3. Die vorhandene Beschreibung beibehalten: `TV Guide integration for Home Assistant`.

Bei Beginn der Vorbereitung waren Issues deaktiviert und keine Topics gesetzt. Das sind echte HACS-Anforderungen; solange sie fehlen, schlägt die strenge Prüfung fehl. Diese Einstellungen lassen sich nicht durch Dateien im Repository aktivieren.

## 2. Alle Prüfungen erfolgreich abschließen

Unter [Actions](https://github.com/criticallimit/HA-TV-Guide/actions) müssen **Validate integration** und **Validate HACS** für den vorgesehenen Stand erfolgreich sein. Nach einer Änderung der Repository-Einstellungen kann **Validate HACS → Run workflow → main** erneut gestartet werden.

## 3. Erste Version veröffentlichen

1. [Neues Release öffnen](https://github.com/criticallimit/HA-TV-Guide/releases/new).
2. Als Tag **`v1.0.0`** eingeben und auf dem geprüften **main** erstellen. Die Manifest-Version bleibt `1.0.0`.
3. Titel: **TV Guide 1.0.0**. Die automatische Seitenleiste, optionale Karte mit Theme-Auswahl, zehn TV-Länder, persönliche Senderlisten, gespeicherte Sendungen, Erinnerungen, Sensoren und Kalender beschreiben. Es wird keine separate Changelog-Datei geführt.
4. Zunächst **Save draft** verwenden und den Zielstand kontrollieren. Wenn alle Prüfungen erfolgreich sind und die Version freigegeben werden soll, **Publish release** wählen. Für eine reguläre stabile Veröffentlichung **Pre-release** nicht aktivieren.

Ein Tag allein genügt nicht für die HACS-Versionsauswahl: Dazu muss das GitHub-Release veröffentlicht sein. Zusätzliche ZIP-Anhänge sind bei dieser Konfiguration optional. Bei späteren Versionen zuerst die Manifest-Version erhöhen, prüfen und danach das passende Release erstellen.

## 4. Installation über HACS testen

Schon vor Aufnahme in den Standardkatalog kann das Repository benutzerdefiniert hinzugefügt werden:

1. HACS öffnen → Menü → **Benutzerdefinierte Repositories**.
2. `https://github.com/criticallimit/HA-TV-Guide` hinzufügen, Kategorie **Integration**.
3. TV Guide herunterladen und Home Assistant neu starten.
4. Bei einer Neuinstallation TV Guide unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** hinzufügen. Bei einer bestehenden Installation den vorhandenen Eintrag behalten.
5. Seitenleiste, Ersteinrichtung, Logo-/EPG-Fortschritt, Länderwechsel, persönliche Sender, gespeicherte Sendungen und Erinnerung testen. Optional die Karte über die visuelle Kartenauswahl hinzufügen und die Theme-Auswahl prüfen.

[Direkt in HACS öffnen](https://my.home-assistant.io/redirect/hacs_repository/?owner=criticallimit&repository=HA-TV-Guide&category=integration).

## 5. Aufnahme in den Standardkatalog beantragen

1. Als Repository-Inhaber `criticallimit` [hacs/default](https://github.com/hacs/default) in das persönliche GitHub-Konto forken.
2. Im Fork einen neuen Branch von `master` erstellen, z. B. `add-ha-tv-guide`.
3. Die vorhandene JSON-Liste in der Datei **`integration`** alphabetisch um **`"criticallimit/HA-TV-Guide"`** ergänzen. Groß-/Kleinschreibung genau übernehmen und die Datei als gültiges JSON erhalten.
4. Einen Pull Request an `hacs/default:master` öffnen, Titel z. B. **Add HA-TV-Guide integration**. Änderungen durch Maintainer erlauben. Die jeweils aktuelle PR-Vorlage vollständig und wahrheitsgemäß ausfüllen.
5. Auf das geprüfte veröffentlichte Release und die erfolgreichen eigenen HACS-/Hassfest-Prüfungen verweisen. Erst nach erfolgreicher Prüfung alle zutreffenden Kästchen der Vorlage bestätigen.
6. Nach Aufnahme und dem nächsten HACS-Scan erscheint TV Guide regulär in der Suche. Bearbeitungsdauer und Freigabe liegen bei den HACS-Maintainern.

Beschreibung für den Antrag:

> TV Guide is a native Home Assistant custom integration for TV schedules in AT, BE, CH, DE, DK, FR, GB, NL, NO and SE. It provides an automatically registered sidebar, an optional visual dashboard card, personal channel lists, saved programmes, native reminders, sensors and a calendar. Country and language follow Home Assistant at first setup. The integration includes local brand assets. Repository: https://github.com/criticallimit/HA-TV-Guide

Es wird ausschließlich dieses Integrationsrepository eingereicht. Das alte Add-on-Repository gehört nicht in diesen Antrag. Die Vorbereitung allein veröffentlicht weder ein Release noch einen Antrag an HACS.

## Offizielle Grundlagen

- [Allgemeine Anforderungen und hacs.json](https://hacs.dev/docs/publish/start/)
- [Anforderungen an Integrationen](https://hacs.dev/docs/publish/integration/)
- [Offizielle HACS-Action](https://hacs.dev/docs/publish/action/)
- [Aufnahme in den Standardkatalog](https://hacs.dev/docs/publish/include/)
- [Aktueller Validator für lokale Brand-Icons](https://github.com/hacs/integration/blob/main/custom_components/hacs/validate/brands.py)

Einzelne Dokumentationsseiten erwähnen weiterhin ausschließlich das zentrale Brands-Repository. Maßgeblich für die hier geprüfte lokale Icon-Unterstützung ist der verlinkte aktuelle HACS-Prüfcode. Die externe HACS-Prüfung wird deshalb vollständig ausgeführt.
