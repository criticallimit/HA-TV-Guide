"""Bounded TV Guide snapshots in the reference frontend's presentation model."""
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

COUNTRY_NAMES={'de':'Deutschland','at':'Österreich','ch':'Schweiz','nl':'Niederlande','be':'Belgien','dk':'Dänemark','no':'Norwegen','fr':'Frankreich','se':'Schweden','gb':'Großbritannien'}
UI_DEFAULTS={'language':'auto','default_view':'now','columns_desktop':5,'max_channels':0,'theme_mode':'auto','refresh_minutes':180,'notification_service':'persistent_notification.create'}
MAX_DISPLAY_CHANNELS=200

@lru_cache(maxsize=1)
def logo_catalog():
    return json.loads((Path(__file__).parent/'frontend'/'app'/'logo_catalog.json').read_text(encoding='utf-8'))

def ui_settings(options):
    return {**UI_DEFAULTS,**{key:options[key] for key in UI_DEFAULTS if key in options},'country':options.get('country','')}

def normalize_ui_settings(values):
    """Validate all UI writes before touching config-entry options."""
    if not isinstance(values,dict):
        raise ValueError('Invalid settings')
    result={}
    allowed={'country':set(COUNTRY_NAMES)|{''},'language':{'auto','de','en','da','nl','fr','it','nb','sv'},'default_view':{'now','1800','2015','2200'},'theme_mode':{'auto','light','dark'}}
    for key, choices in allowed.items():
        if key in values:
            if values[key] not in choices:
                raise ValueError('Invalid '+key)
            result[key]=values[key]
    for key,minimum,maximum in [('columns_desktop',3,6),('max_channels',0,MAX_DISPLAY_CHANNELS)]:
        if key in values:
            value=values[key]
            if type(value) is not int or not minimum<=value<=maximum:
                raise ValueError('Invalid '+key)
            result[key]=value
    if 'refresh_minutes' in values:
        if type(values['refresh_minutes']) is not int or values['refresh_minutes'] not in (30,60,120,180,360,720,1440):
            raise ValueError('Invalid refresh interval')
        result['refresh_minutes']=values['refresh_minutes']
    if 'notification_service' in values:
        value=values['notification_service']
        if not isinstance(value,str) or (value!='persistent_notification.create' and not (value.startswith('notify.') and value[7:] and value[7:].isascii() and value[7:].replace('_','').isalnum())):
            raise ValueError('Invalid notification service')
        result['notification_service']=value
    if set(values)-set(UI_DEFAULTS)-{'country'}:
        raise ValueError('Unknown settings')
    return result

def presentation_channels(catalogue,feed_channels,country):
    main=[dict(item) for item in catalogue]
    mapped={item.get('xmltv_id') for item in main}
    extra=[{'id':item['id'],'name':item['name'],'xmltv_id':item['id'],'available':True} for item in feed_channels if item['id'] not in mapped]
    logos=logo_catalog().get(country,{})
    return [{**item,**logos.get(item['id'],{}),'source_country':country,'source_channel_id':item['id']} for item in main+extra]

def personal_payload(catalogue,feed_channels,options):
    country=options.get('country','')
    channels=presentation_channels(catalogue,feed_channels,country)
    aliases={item.get('xmltv_id'):item['id'] for item in channels if item.get('xmltv_id')}
    known={item['id'] for item in channels}
    selected=options.get('channels',[])
    order=list(dict.fromkeys(aliases.get(key,key) for key in selected if aliases.get(key,key) in known)) if selected else [item['id'] for item in channels[:MAX_DISPLAY_CHANNELS]]
    return {'channels':channels,'order':order,'countries':[country],'supported_countries':[{'code':country,'name':COUNTRY_NAMES.get(country,'XMLTV')} ]}

def guide_at(payload, at):
    """Copy a full provider view into a bounded timestamp window for HA actions."""
    channels = []
    for channel in payload.get('channels', []):
        programmes = []
        for item in channel.get('programs', []):
            try:
                start = datetime.fromisoformat(item['start'])
                end = datetime.fromisoformat(item['end'])
            except (KeyError, TypeError, ValueError):
                continue
            if start.tzinfo is not None and end.tzinfo is not None and end > start and end > at:
                programmes.append(item)
        programmes.sort(key=lambda item: datetime.fromisoformat(item['start']).timestamp())
        channels.append({**channel, 'programs': programmes[:7]})
    return {**payload, 'channels': channels}


def guide_preview(payload, body):
    """First paint uses the same seven rows and default time as the full view."""
    at = datetime.now(timezone.utc)
    try:
        candidate = datetime.fromisoformat(body.get('at', ''))
        if candidate.tzinfo is not None:
            at = candidate.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        local = at.astimezone(ZoneInfo(body.get('time_zone', 'UTC')))
    except (TypeError, ValueError, OverflowError, ZoneInfoNotFoundError):
        local = at
    mode = payload.get('ui', {}).get('default_view', 'now')
    if mode in ('1800', '2015', '2200'):
        local = local.replace(hour=int(mode[:2]), minute=int(mode[2:]), second=0, microsecond=0)
    return {**guide_at(payload, local), '_preview': True}


def build_guide(programmes,catalogue,feed_channels,options,at,refresh_running=False):
    """Return seven rows per visible sender; never transfer the whole feed to the UI."""
    country=options.get('country','')
    channels=presentation_channels(catalogue,feed_channels,country)
    preferences=personal_payload(catalogue,feed_channels,options)
    main=[item['id'] for item in catalogue] or [item['id'] for item in channels]
    custom=preferences['order']
    limit=options.get('max_channels',0) or MAX_DISPLAY_CHANNELS
    main=main[:limit];custom=custom[:limit]
    ids=list(dict.fromkeys(main+custom))
    visible={item['id']:item for item in channels if item['id'] in ids}
    needed={item.get('xmltv_id') for item in visible.values() if item.get('xmltv_id')}
    grouped={key:[] for key in needed}
    latest=None
    for item in programmes:
        if item.get('channel') not in needed:
            continue
        try:
            start=datetime.fromisoformat(item['start']);end=datetime.fromisoformat(item['stop'])
        except (KeyError,TypeError,ValueError):
            continue
        if start.tzinfo is None or end.tzinfo is None or end<=start:
            continue
        latest=max(latest,end) if latest is not None else end
        if end<=at:
            continue
        key=f"{item['channel']}\n{start.astimezone(timezone.utc).isoformat()}"
        grouped[item['channel']].append({'id':'guide_'+sha256(key.encode()).hexdigest(),'title':item['title'],'start':item['start'],'end':item['stop'],'desc':item.get('description',''),'subtitle':item.get('subtitle',''),'category':item.get('category','')})
    for records in grouped.values():
        records.sort(key=lambda item:datetime.fromisoformat(item['start']).timestamp())
    for channel in visible.values():
        channel['programs']=grouped.get(channel.get('xmltv_id'),[])[:7]
        channel['data_state']='available' if channel['programs'] else 'no_programmes'
    return {'channels':[visible[key] for key in ids if key in visible],'main_channel_ids':main,'custom_channel_ids':custom,'country':country,'ui':ui_settings(options),'refresh_running':refresh_running,'feed_latest_end':latest.isoformat() if latest else None}
