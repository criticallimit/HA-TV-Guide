"""Programme value helpers: names, XMLTV timestamps and stable channel IDs."""
import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

EPG_TIMEZONE = ZoneInfo("Europe/Berlin")

def normalize(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower().replace("&", "und")
    value = re.sub(r"\b(hd|uhd|sd)\b", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)

def xmltv_datetime(value):
    value = (value or "").strip()
    if not value:
        return None
    m = re.fullmatch(r"(\d{8}(?:\d{2}){0,3})(?:\s*([+-]\d{4}|Z))?", value)
    if not m:
        return None
    base, offset = m.groups()
    # XMLTV permits reduced precision; pad missing time fields with zeros.
    base = (base + "000000")[0:14]
    try:
        dt = datetime.strptime(base, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    if offset == "Z":
        dt = dt.replace(tzinfo=timezone.utc)
    elif offset:
        sign = 1 if offset[0] == "+" else -1
        hours = int(offset[1:3])
        minutes = int(offset[3:5])
        if hours > 23 or minutes > 59:
            return None
        dt = dt.replace(tzinfo=timezone(sign * timedelta(hours=hours, minutes=minutes)))
    else:
        dt = dt.replace(tzinfo=EPG_TIMEZONE)
    return dt.astimezone(EPG_TIMEZONE)

def first_text(node, tag):
    child = node.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""

def feed_channel_id(source_id):
    digest = hashlib.sha1(str(source_id or "").encode("utf-8")).hexdigest()[:16]
    return f"epg_{digest}"
