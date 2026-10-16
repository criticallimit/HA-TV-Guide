"""Read immutable logo metadata directly from the installed package."""
import json
from pathlib import Path
from zipfile import ZipFile


def load_logo_metadata():
    with ZipFile(Path(__file__).with_name('reference-data.zip')) as archive:
        library = json.loads(archive.read('data/logo_library.json'))
        updates = json.loads(archive.read('data/logo_updates.json'))
        for part in updates['library_parts']:
            additions = json.loads(archive.read('data/' + part))
            library['channels'].update(additions['channels'])
            library['assets'].update(additions['assets'])
        europe = json.loads(archive.read('data/europe_logo_library.json'))
    return library, europe
