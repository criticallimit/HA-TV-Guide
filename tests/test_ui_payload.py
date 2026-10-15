"""TV Guide UI model bounds, aliases, IDs, settings and reference-asset provenance."""
from datetime import datetime,timezone,timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]/'custom_components'/'tv_guide'
spec=importlib.util.spec_from_file_location('_tvguide_ui_payload_tests',ROOT/'ui_payload.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)

class UIPayloadTests(unittest.TestCase):
    def setUp(self):
        self.at=datetime(2026,10,14,18,tzinfo=timezone.utc)
        self.catalogue=[{'id':'ard','name':'Das Erste','xmltv_id':'DasErste.de','available':True},{'id':'zdf','name':'ZDF','xmltv_id':None,'available':False}]
        self.feed=[{'id':'DasErste.de','name':'ARD'},{'id':'extra.tv','name':'Extra'}]
        self.records=[{'channel':'DasErste.de','title':str(i),'start':(self.at+timedelta(hours=i)).isoformat(),'stop':(self.at+timedelta(hours=i+1)).isoformat(),'description':'Description','category':'News'} for i in range(20)]

    def test_original_model_has_seven_rows_stable_ids_and_unavailable_senders(self):
        result=ui.build_guide(self.records,self.catalogue,self.feed,{'country':'de','channels':['DasErste.de']},self.at)
        self.assertEqual(result['main_channel_ids'],['ard','zdf'])
        self.assertEqual(result['custom_channel_ids'],['ard'])
        first=result['channels'][0]
        self.assertEqual(len(first['programs']),7)
        self.assertEqual(result['feed_latest_end'],(self.at+timedelta(hours=20)).isoformat())
        self.assertEqual(first['programs'][0]['desc'],'Description')
        self.assertEqual(first['programs'][0]['category'],'News')
        self.assertTrue(first['programs'][0]['id'].startswith('guide_'))
        self.assertEqual(result['channels'][1]['programs'],[])
        self.assertTrue((ROOT/'frontend'/'app'/first['logo_normalized_light']).is_file())

    def test_requested_time_and_offsets_select_correct_rows(self):
        self.records[0]['start']=self.at.astimezone(timezone(timedelta(hours=3))).isoformat()
        result=ui.build_guide(self.records,self.catalogue,self.feed,{'country':'de'},self.at+timedelta(hours=9))
        first=result['channels'][0]['programs']
        self.assertEqual(first[0]['title'],'9')
        self.assertEqual(len(first),7)

    def test_personal_sender_order_and_raw_alias_resolve_without_duplicates(self):
        result=ui.personal_payload(self.catalogue,self.feed,{'country':'de','channels':['extra.tv','DasErste.de','ard','zdf']})
        self.assertEqual(result['order'],['extra.tv','ard','zdf'])
        self.assertEqual(result['supported_countries'],[{'code':'de','name':'Deutschland'}])

    def test_all_channel_default_and_display_bound(self):
        feed=[{'id':str(i),'name':str(i)} for i in range(400)]
        result=ui.build_guide([],[],feed,{},self.at)
        self.assertLessEqual(len(result['channels']),200)
        self.assertEqual(len(result['main_channel_ids']),200)

    def test_settings_validation_rejects_invalid_writes(self):
        for values in ({'country':'bad'},{'columns_desktop':7},{'max_channels':-1},{'refresh_minutes':1},{'theme_mode':'other'},{'notification_service':'shell.execute'},{'unknown':'x'},{'columns_desktop':True}):
            with self.subTest(values=values),self.assertRaises(ValueError):ui.normalize_ui_settings(values)
        result=ui.normalize_ui_settings({'country':'de','columns_desktop':5,'refresh_minutes':60,'notification_service':'notify.mobile_app_test'})
        self.assertEqual(result['notification_service'],'notify.mobile_app_test')

    def test_styles_and_renderer_match_pinned_reference(self):
        app=ROOT/'frontend'/'app'
        provenance=json.loads((app/'REFERENCE.json').read_text(encoding='utf-8'))
        for name in ('styles.css','guide-core.js','channel-picker.js','translations.js','i18n.js'):
            bundled = (app/name).read_bytes()
            original = (ROOT.parents[1]/'tests'/'reference-frontend'/name).read_bytes()
            self.assertEqual(hashlib.sha256(bundled).hexdigest(),provenance['bundled_sha256'][name],name)
            self.assertEqual(hashlib.sha256(original).hexdigest(),provenance['source_sha256'][name],name)
            self.assertEqual(bundled.replace(b'\r\n', b'\n'), original.replace(b'\r\n', b'\n'), name)
        logos=json.loads((app/'logo_catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(len(logos),10)
        for country in logos.values():
            for channel in country.values():
                for asset in channel.values():self.assertTrue((app/asset).is_file(),asset)

if __name__=='__main__':unittest.main()
