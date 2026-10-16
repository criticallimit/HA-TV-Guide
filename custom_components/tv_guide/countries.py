"""Shared country registrations for sources, catalogues and presentation."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
COUNTRIES = json.loads((ROOT / "countries.json").read_text(encoding="utf-8"))
COUNTRY_NAMES = {code: item["name"] for code, item in COUNTRIES.items()}
COUNTRY_ALIASES = {alias: code for code, item in COUNTRIES.items() for alias in item.get("aliases", [])}
CATALOG_FILES = {code: item["catalog"] for code, item in COUNTRIES.items()}
COUNTRY_FEEDS = {code: item["sources"][0] for code, item in COUNTRIES.items()}
COUNTRY_FALLBACKS = {code: tuple(item["sources"][1:]) for code, item in COUNTRIES.items() if len(item["sources"]) > 1}
LANGUAGE_COUNTRIES = {}
for code, item in COUNTRIES.items():
    if item.get("language"):
        LANGUAGE_COUNTRIES.setdefault(item["language"], code)
