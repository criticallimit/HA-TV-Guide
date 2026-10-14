"""Original reminder translations for native HA delivery."""
from functools import lru_cache
import json
from pathlib import Path
import zipfile


@lru_cache(maxsize=8)
def _catalogue(language):
    with zipfile.ZipFile(Path(__file__).parent/'original_backend'/'reference-data.zip') as archive:
        return json.loads(archive.read('www/locales/'+language+'.json'))


def reminder_text(item, time_text, fallback_language='de'):
    """Call in HA's executor: loading the catalogue performs file I/O."""
    language=str(item.get('language') or fallback_language).lower().replace('_','-').split('-')[0]
    if language=='auto':language=fallback_language.split('-')[0]
    if language=='no':language='nb'
    if language not in {'de','en','nl','fr','it','da','nb','sv'}:language='en'
    catalogue=_catalogue(language)
    title=catalogue.get('TV Guide – Erinnerung','TV Guide – Reminder')
    template=catalogue.get('{channel}: „{title}“ beginnt um {time} Uhr.','{channel}: “{title}” starts at {time}.')
    return {'title':title,'message':template.format(channel=item['channel'],title=item['title'],time=time_text)}
