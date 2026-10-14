"""Verified source URLs and German broadcaster/teletext registrations.

Country-specific registrations remain in data/countries.json.
"""

OPEN_EPG_URL = "https://www.open-epg.com/files/germany.xml.gz"

EPGSHARE_EPG_URL = "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz"

EPGPW_EPG_URL = "https://epg.pw/xmltv/epg_DE.xml.gz"

BUILTIN_EPG_URLS = [OPEN_EPG_URL, EPGSHARE_EPG_URL]

ARD_RB_PROGRAM_URL = "https://www.ardmediathek.de/radiobremen/programm/{date}"

SWR_PROGRAM_URL = "https://www.swr.de/video/tv-programm/index.html?swx_pcDate={date}&swx_pcStation=7.0.0"

SR_PROGRAM_URL = "https://www.sr.de/sr/epg/tv/srtv/station108~_day-{date}.html"

ARD_PROGRAM_URL = "https://www.ardmediathek.de/programm/{date}"

ZDF_PROGRAM_URL = "https://www.zdf.de/live-tv"

OFFICIAL_PROVIDER_BY_CHANNEL = {
    "ard": {"kind": "ard", "marker": "Das Erste"},
    "zdf": {"kind": "zdf", "marker": "ZDF"},
    "rtl": {"kind": "generic", "url": "https://www.rtl.de/fernsehprogramm/rtl/{date}/"},
    "sat1": {"kind": "generic", "url": "https://www.sat1.de/tv-programm"},
    "prosieben": {"kind": "generic", "url": "https://www.prosieben.de/tv-programm"},
    "kabeleins": {"kind": "generic", "url": "https://www.kabeleins.de/tv-programm"},
    "rtlzwei": {"kind": "generic", "url": "https://www.rtl2.de/tv-programm/{date}"},
    "vox": {"kind": "generic", "url": "https://www.rtl.de/fernsehprogramm/vox/{date}/"},
    "arte": {"kind": "ard", "marker": "arte"},
    "3sat": {"kind": "ard", "marker": "3sat"},
    "ndr": {"kind": "ard", "marker": "NDR"},
    "wdr": {"kind": "ard", "marker": "WDR"},
    "mdr": {"kind": "ard", "marker": "MDR"},
    "rbb": {"kind": "ard", "marker": "RBB"},
    "br": {"kind": "ard", "marker": "BR"},
    "swr": {"kind": "swr"},
    "sr": {"kind": "sr"},
    "hr": {"kind": "ard", "marker": "hr"},
    "radiobremen": {"kind": "radiobremen"},
    "ardalpha": {"kind": "ard", "marker": "ARD alpha"},
    "phoenix": {"kind": "ard", "marker": "phoenix"},
    "tagesschau24": {"kind": "ard", "marker": "tagesschau24"},
    "zdfneo": {"kind": "zdf", "marker": "ZDFneo"},
    "zdfinfo": {"kind": "zdf", "marker": "ZDFinfo"},
    "one": {"kind": "ard", "marker": "ONE"},
    "welt": {"kind": "generic", "url": "https://www.welt.de/tv-programm-live-stream/"},
    "ntv": {"kind": "generic", "url": "https://www.n-tv.de/mediathek/tv/"},
    "disneychannel": {"kind": "generic", "url": "https://tv.disney.de/tv-programm"},
    "n24doku": {"kind": "generic", "url": "https://www.welt.de/tv-programm-n24-doku/"},
    "sixx": {"kind": "generic", "url": "https://www.sixx.de/tv-programm"},
    "prosiebenmaxx": {"kind": "generic", "url": "https://www.prosiebenmaxx.de/tv-programm"},
    "dmax": {"kind": "generic", "url": "https://dmax.de/tv-programm"},
    "sat1gold": {"kind": "generic", "url": "https://www.sat1gold.de/tv-programm"},
    "voxup": {"kind": "generic", "url": "https://www.rtl.de/fernsehprogramm/vox-up/{date}/"},
    "rtlup": {"kind": "generic", "url": "https://www.rtl.de/fernsehprogramm/rtl-up/{date}/"},
    "weltderwunder": {"kind": "generic", "url": "https://www.weltderwunder.de/live-tv/"},
    "df1": {"kind": "generic", "url": "https://df1.de/"},
    "tlc": {"kind": "generic", "url": "https://tlc.de/im-tv"},
    "nitro": {"kind": "generic", "url": "https://www.rtl.de/fernsehprogramm/nitro/{date}/"},
    "tele5": {"kind": "generic", "url": "https://tele5.de/"},
    "superrtl": {"kind": "generic", "url": "https://www.rtl.de/fernsehprogramm/super-rtl/{date}/"},
    "kika": {"kind": "ard", "marker": "KiKA"},
    "eurosport1": {"kind": "generic", "url": "https://www.eurosport.de/watch/schedule.shtml"},
    "sport1": {"kind": "generic", "url": "https://www.sport1.de/tv-video/tv"},
    "esportsone": {"kind": "generic", "url": "https://start.sportdigital.de/tvsender/esportsone"},
    "kabeleinsdoku": {"kind": "generic", "url": "https://www.kabeleinsdoku.de/"},
}

TELETEXT_PROVIDER_BY_CHANNEL = {
    "ard": {
        "today": [f"https://origin.ard-text.de/mobil/{page}" for page in range(301, 305)],
        "tomorrow": [f"https://origin.ard-text.de/mobil/{page}" for page in range(305, 309)],
    },
    "zdf": {
        "today": [f"https://teletext.zdf.de/teletext/zdf/seiten/{page}.html" for page in range(301, 305)],
        "tomorrow": [f"https://teletext.zdf.de/teletext/zdf/seiten/{page}.html" for page in range(350, 354)],
    },
    "zdfneo": {
        "today": [f"https://teletext.zdf.de/teletext/zdfneo/seiten/{page}.html" for page in range(301, 305)],
        "tomorrow": [f"https://teletext.zdf.de/teletext/zdfneo/seiten/{page}.html" for page in range(350, 354)],
    },
    "zdfinfo": {
        "today": [f"https://teletext.zdf.de/teletext/zdfinfo/seiten/{page}.html" for page in range(301, 305)],
        "tomorrow": [f"https://teletext.zdf.de/teletext/zdfinfo/seiten/{page}.html" for page in range(350, 354)],
    },
    "3sat": {
        "today": [f"https://teletext.zdf.de/teletext/3sat/seiten/{page}.html" for page in range(301, 305)],
        "tomorrow": [f"https://teletext.zdf.de/teletext/3sat/seiten/{page}.html" for page in range(350, 354)],
    },
    "wdr": {
        "today": [f"https://mobiltext.wdr.de/{page}.html" for page in range(301, 305)],
        "tomorrow": [f"https://mobiltext.wdr.de/{page}.html" for page in range(325, 329)],
    },
    "ndr": {
        "today": [f"https://www.ndr.de/public/teletext/{page}_01.htm" for page in range(301, 306)],
        "tomorrow": [f"https://www.ndr.de/public/teletext/{page}_01.htm" for page in range(306, 311)],
    },
}

SECONDARY_WEB_PROVIDER_BY_CHANNEL = {
    "euronews": "https://tvgid.de/channels/de-euron-d?date={date}",
    "hgtv": "https://tvgid.de/channels/de-hgtv?date={date}",
    "nickelodeon": "https://tvgid.de/channels/de-nick?date={date}",
    "comedycentral": "https://tvgid.de/channels/de-comedy-central?date={date}",
}
