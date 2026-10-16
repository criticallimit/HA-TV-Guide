"""TV Guide reminder translations for Home Assistant notifications."""
from .languages import messages, normalize_language


def reminder_text(item, time_text, fallback_language='de'):
    """Call in HA's executor: loading the catalogue performs file I/O."""
    configured=str(item.get('language') or fallback_language)
    if configured.lower()=='auto':
        configured=str(fallback_language or 'en')
    language=normalize_language(configured)
    catalogue=messages(language)
    english=messages('en')
    title=catalogue.get('TV Guide – Erinnerung') or english.get('TV Guide – Erinnerung','TV Guide – Reminder')
    template=catalogue.get('{channel}: „{title}“ beginnt um {time} Uhr.') or english.get('{channel}: „{title}“ beginnt um {time} Uhr.','{channel}: “{title}” starts at {time}.')
    return {'title':title,'message':template.format(channel=item['channel'],title=item['title'],time=time_text)}
