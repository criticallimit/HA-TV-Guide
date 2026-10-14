"""Shared JSON persistence for user settings and saved programme lists."""
import json
import os


def read_json_file(path, default):
    """Use defaults when a user file is unavailable, invalid or has the wrong root type."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def write_json_file(path, value):
    """Replace the destination only after the complete JSON has been written."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
