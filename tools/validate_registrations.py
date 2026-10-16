"""Validate country/catalogue registrations and translation source files offline."""
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/tv_guide'


def validate(root=ROOT):
    errors=[]
    def fail(where, message): errors.append(f'{where}: {message}')
    def load(path):
        try:
            def unique(pairs):
                result={}
                for key,value in pairs:
                    if key in result:raise ValueError('Duplicate JSON key: '+key)
                    result[key]=value
                return result
            value=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)
            if not isinstance(value,dict):raise ValueError('expected an object')
            return value
        except (OSError,ValueError) as error:
            fail(str(path.relative_to(root)),str(error));return {}
    def aliases(registry, label):
        seen=set(registry)
        for code,item in registry.items():
            if not isinstance(item,dict):fail(label+'.'+code,'expected an object');continue
            values=item.get('aliases',[])
            if not isinstance(values,list):fail(label+'.'+code,'aliases must be a list');continue
            for alias in values:
                pattern=r'[a-z]{2,3}(?:-[a-z0-9]{2,8})*' if label=='languages' else r'[a-z]{2}'
                if not isinstance(alias,str) or not re.fullmatch(pattern,alias) or alias in seen:
                    fail(label+'.'+code,'invalid or duplicate alias '+str(alias))
                else:seen.add(alias)
    def url(value):
        if not isinstance(value,str):return False
        try:
            parsed=urlsplit(value)
            return parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password
        except ValueError:return False
    languages=load(root/'languages.json');countries=load(root/'countries.json')
    aliases(languages,'languages');aliases(countries,'countries')
    locales={}
    for code,item in languages.items():
        if not re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]{2,8})*',code):fail(code,'invalid language code');continue
        if not isinstance(item,dict) or not isinstance(item.get('name'),str) or not item['name'].strip():fail(code,'missing language name')
        locales[code]=load(root/'locales'/f'{code}.json')
    english=locales.get('en',{}).get('messages',{})
    if not isinstance(english,dict) or not english:
        fail('en','English fallback messages are required');english={}
    def leaves(value,prefix=''):
        if not isinstance(value,dict):return {prefix:value}
        return {k:v for key,item in value.items() for k,v in leaves(item,prefix+'.'+key).items()}
    class MarkupMessages(HTMLParser):
        def handle_starttag(self,tag,attrs):
            for name,value in attrs:
                if name=='data-i18n' or name.startswith('data-i18n-'):
                    if value and value not in english:fail('view.html','missing English UI text: '+value)
    view=root/'frontend/app/view.html'
    if view.exists():MarkupMessages().feed(view.read_text(encoding='utf-8'))
    for path in (root/'frontend/app').glob('*.js'):
        if path.name in {'translations.js','view-template.js'}:continue
        for token in re.findall(r"\bt\(\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')",path.read_text(encoding='utf-8')):
            key=ast.literal_eval(token)
            if key not in english:fail(path.name,'missing English UI text: '+key)
    ha_english=leaves(locales.get('en',{}).get('home_assistant',{}))
    if not locales.get('en',{}).get('home_assistant'):fail('en','Home Assistant fallback texts are required')
    for code,locale in locales.items():
        texts=locale.get('messages',{})
        if not isinstance(texts,dict):fail(code,'messages must be an object');continue
        for key in set(english)|set(texts):
            value=texts.get(key)
            if not isinstance(value,str) or not value.strip():fail(code,'missing text: '+key);continue
            if key not in english:fail(code,'unknown translation key: '+key);continue
            if not isinstance(english[key],str):continue
            if set(re.findall(r'\{(\w+)\}',english[key])) != set(re.findall(r'\{(\w+)\}',value)):
                fail(code,'mismatched placeholders: '+key)
        ha=leaves(locale.get('home_assistant',{}))
        for key in set(ha_english)|set(ha):
            if key not in ha_english or not isinstance(ha.get(key),str) or not ha[key].strip():fail(code,'invalid HA translation: '+key)
            elif isinstance(ha_english[key],str) and set(re.findall(r'\{(\w+)\}',ha_english[key])) != set(re.findall(r'\{(\w+)\}',ha[key])):
                fail(code,'mismatched HA placeholders: '+key)
    logo_entries=load(root/'logo_library/index.json').get('entries',{})
    for code,item in countries.items():
        if not re.fullmatch(r'[a-z]{2}',code):fail(code,'invalid country code')
        if not isinstance(item,dict):continue
        if not isinstance(item.get('name'),str) or not item['name'].strip():fail(code,'missing country name')
        try:ZoneInfo(item.get('timezone',''))
        except (ZoneInfoNotFoundError,ValueError,TypeError):fail(code,'invalid timezone')
        for field in ('storage_prefix','source_id_prefix'):
            if field in item and (not isinstance(item[field],str) or not re.fullmatch(r'[a-z0-9_-]*',item[field])):
                fail(code,'invalid '+field)
        if item.get('language') and (not isinstance(item['language'],str) or item['language'] not in languages):fail(code,'unregistered fallback language')
        prefixes=item.get('display_name_prefixes',[])
        if not isinstance(prefixes,list) or any(not isinstance(value,str) or not value for value in prefixes):
            fail(code,'invalid display name prefixes')
        sources=item.get('sources')
        if not isinstance(sources,list) or not sources or any(not url(source) for source in sources):fail(code,'sources must be HTTPS URLs')
        elif len(sources)!=len(set(sources)):fail(code,'duplicate source URL')
        catalog=item.get('catalog','')
        if not isinstance(catalog,str) or Path(catalog).name!=catalog or not catalog.endswith('.json'):
            fail(code,'invalid catalogue filename');continue
        channels=load(root/'catalogs'/catalog).get('channels',[])
        if not isinstance(channels,list) or not channels:fail(code,'missing channel catalogue');continue
        ids=set();orders=set()
        for channel in channels:
            if not isinstance(channel,dict):fail(code,'channel must be an object');continue
            ident=channel.get('id');order=channel.get('order')
            if not isinstance(ident,str) or not ident or ':' in ident or ident in ids:fail(code,'invalid or duplicate sender ID '+str(ident))
            else:ids.add(ident)
            if type(order) is not int or order < 0 or order in orders:fail(code,'invalid or duplicate sender order '+str(order))
            else:orders.add(order)
            if not isinstance(channel.get('name'),str) or not channel['name'].strip():fail(code,'missing sender name')
            xmltv=channel.get('xmltv_ids',[])
            if not isinstance(xmltv,list) or any(not isinstance(value,str) or not value for value in xmltv):fail(code,'invalid XMLTV IDs')
            for field in ('logo_file','logo_file_light'):
                if channel.get(field) and channel[field] not in logo_entries:fail(code,'unknown logo reference '+str(channel[field]))
        for field in ('providers','secondary_providers','secondary_urls','teletext_providers'):
            providers=item.get(field,{})
            if not isinstance(providers,dict):fail(code,'invalid '+field);continue
            for ident,provider in providers.items():
                if ident not in ids:fail(code,field+' references unknown sender '+ident)
                if field=='secondary_urls':
                    if not url(provider):fail(code,'invalid secondary provider URL')
                elif not isinstance(provider,dict):fail(code,'invalid provider '+ident)
                elif field=='teletext_providers':
                    for values in provider.values():
                        if not isinstance(values,list) or any(not url(value) for value in values):fail(code,'invalid teletext URLs '+ident)
                elif not isinstance(provider.get('kind'),str) or not provider['kind']:
                    fail(code,'missing provider adapter kind '+ident)
                elif 'url' in provider and not url(provider['url']):fail(code,'invalid provider URL '+ident)
    registered={code+'.json' for code in languages}
    for path in (root/'locales').glob('*.json'):
        if path.name not in registered:fail(path.name,'locale has no language registration')
    for path in (root/'translations').glob('*.json'):
        if path.name not in registered:fail(path.name,'HA translation has no language registration')
    return errors


if __name__=='__main__':
    problems=validate()
    if problems:raise SystemExit('\n'.join(problems))
    print('Country registrations, sender catalogues, logo references and translations are valid')
