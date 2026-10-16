"""Registry validation, generated files and extension without runtime edits."""
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from native_support import module

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('validate_registrations',ROOT/'tools/validate_registrations.py')
validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
sys.modules['validate_registrations']=validator
spec=importlib.util.spec_from_file_location('_build_locales',ROOT/'tools/build_locales.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)/'tv_guide'
        shutil.copytree(validator.ROOT,self.root,ignore=shutil.ignore_patterns('__pycache__'))

    def edit(self,path,change):
        file=self.root/path;value=json.loads(file.read_text());change(value)
        file.write_text(json.dumps(value,ensure_ascii=False))

    def test_current_registrations_and_generated_outputs_match(self):
        self.assertEqual(validator.validate(),[])
        for path,data in builder.build().items():self.assertEqual(path.read_bytes(),data,path)

    def test_invalid_country_and_catalogue_report_all_errors_together(self):
        def damage(value):
            value['de']['timezone']='Missing/Zone';value['de']['sources']=['http://example.org/feed']
            value['de']['language']='missing';value['at']['aliases']=['de']
        self.edit('countries.json',damage)
        def channels(value):
            value['channels'][1]['id']=value['channels'][0]['id']
            value['channels'][0]['logo_file']='logos/missing.svg'
        self.edit('catalogs/channels.json',channels)
        result='\n'.join(validator.validate(self.root))
        for message in ('timezone','HTTPS','fallback language','alias','duplicate sender ID','logo reference'):
            self.assertIn(message,result)

    def test_missing_texts_placeholders_and_ha_names_are_rejected(self):
        def damage(value):
            del value['messages']['Einstellungen']
            value['messages']['{count} angezeigt']='Wrong {total}'
            value['home_assistant']['entity']['sensor']['next_reminder']['name']=''
        self.edit('locales/fr.json',damage)
        result='\n'.join(validator.validate(self.root))
        for message in ('missing text: Einstellungen','mismatched placeholders','invalid HA translation'):
            self.assertIn(message,result)

    def test_invalid_json_and_english_value_types_report_errors_without_crashing(self):
        self.edit('locales/en.json',lambda value:value['messages'].update({'Einstellungen':123}))
        self.edit('languages.json',lambda value:value['fr'].update({'aliases':'invalid'}))
        self.assertIn('missing text: Einstellungen','\n'.join(validator.validate(self.root)))
        (self.root/'languages.json').write_text('{"en":{},"en":{}}')
        self.assertIn('Duplicate JSON key','\n'.join(validator.validate(self.root)))

    def test_new_language_and_country_work_from_data_through_save_restart_and_reminders(self):
        locale=json.loads((self.root/'locales/en.json').read_text())
        locale['messages']['Einstellungen']='Ajustes'
        locale['messages']['TV Guide – Erinnerung']='Recordatorio'
        (self.root/'locales/pt.json').write_text(json.dumps(locale,ensure_ascii=False))
        self.edit('languages.json',lambda value:value.update({'pt':{'name':'Português'}}))
        country={'name':'New country','catalog':'channels_zz.json','timezone':'Pacific/Auckland',
                 'language':'pt','sources':['https://example.org/new.xml.gz']}
        self.edit('countries.json',lambda value:value.update({'zz':country}))
        (self.root/'catalogs/channels_zz.json').write_text(json.dumps({'channels':[
            {'id':'zz_station','order':1,'name':'New station','xmltv_ids':['Station.zz']}]}))
        self.assertEqual(validator.validate(self.root),[])
        for path,data in builder.build(self.root).items():path.write_bytes(data)
        self.assertIn('export const languageRegistry', (self.root/'frontend/app/translations.js').read_text())
        self.assertIn('Ajustes',(self.root/'frontend/app/translations.js').read_text())
        self.assertTrue((self.root/'translations/pt.json').exists())
        name='_tvguide_extended_locale_test';pkg=types.ModuleType(name);pkg.__path__=[str(self.root)]
        with patch.dict(sys.modules,{name:pkg}):
            runtime=importlib.import_module(name+'.guide_runtime').GuideRuntime
            languages=importlib.import_module(name+'.languages')
            self.assertEqual(languages.normalize_language('pt_BR'),'pt')
            payload=importlib.import_module(name+'.ui_payload')
            self.assertEqual(payload.normalize_ui_settings({'language':'pt'}),{'language':'pt'})
            defaults=importlib.import_module(name+'.ha_defaults').installation_defaults
            self.assertEqual(defaults(types.SimpleNamespace(language='pt-BR',country='ZZ'))['country'],'zz')
            storage=self.root/'entry'
            for iteration in range(2):
                backend=runtime(storage,{'country':'zz'},{'language':'pt'},lambda:None)
                try:
                    backend.runtime.start_background=lambda *args,**kwargs:None
                    settings=backend.request('settings','GET')
                    if iteration==0:
                        backend.request('settings','POST',{**settings,'language':'pt'})
                        backend.request('personal-channels','POST',{'order':['zz:zz_station'],'countries':['zz']})
                    self.assertEqual(backend.request('settings','GET')['language'],'pt')
                    self.assertEqual(backend.request('personal-channels','GET')['order'],['zz:zz_station'])
                    self.assertEqual(backend.request('guide','GET')['ui']['language'],'pt')
                finally:backend.close()
            text=importlib.import_module(name+'.notification_text').reminder_text({'language':'pt','channel':'TV','title':'Film'},'20:15')
            self.assertEqual(text['title'],'Recordatorio')

    def test_regional_codes_aliases_and_unknown_languages_use_shared_rules(self):
        normal=module('languages').normalize_language
        for value,expected in [('FR_ca','fr'),('no_NO','nb'),('nb-no','nb'),('EN-us','en'),('unknown','en')]:
            self.assertEqual(normal(value),expected)

    def test_missing_reminder_translation_falls_back_to_english(self):
        notification=module('notification_text')
        with patch.object(notification,'messages',side_effect=lambda language:{'TV Guide – Erinnerung':'Reminder','{channel}: „{title}“ beginnt um {time} Uhr.':'{channel}: {title} at {time}'} if language=='en' else {}):
            value=notification.reminder_text({'language':'fr','channel':'TV','title':'Film'},'20:15')
        self.assertEqual(value,{'title':'Reminder','message':'TV: Film at 20:15'})
