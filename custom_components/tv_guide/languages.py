"""Language registrations shared by settings, installation and reminders."""
from functools import lru_cache
import json
from pathlib import Path

ROOT = Path(__file__).parent
LANGUAGES = json.loads((ROOT / 'languages.json').read_text(encoding='utf-8'))
LANGUAGE_ALIASES = {alias: code for code, item in LANGUAGES.items() for alias in item.get('aliases', [])}


def normalize_language(value, fallback='en'):
    code = str(value or '').lower().replace('_', '-')
    while code:
        resolved = LANGUAGE_ALIASES.get(code, code)
        if resolved in LANGUAGES:
            return resolved
        code = code.rsplit('-', 1)[0] if '-' in code else ''
    return fallback


@lru_cache(maxsize=32)
def messages(language):
    """Read on the executor; translations are shared for the process lifetime."""
    return json.loads((ROOT / 'locales' / (normalize_language(language) + '.json')).read_text(encoding='utf-8'))['messages']
