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
        self.assertTrue(result['_windowed'])
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

    def test_preview_uses_default_view_in_browser_time_zone(self):
        payload = {'ui': {'default_view': '2015'}, 'channels': [{'id': 'ard', 'programs': [
            {'title': str(i), 'start': (self.at+timedelta(minutes=30*i)).isoformat(),
             'end': (self.at+timedelta(minutes=30*(i+1))).isoformat()} for i in range(30)]}]}
        preview = ui.guide_preview(payload, {'at': '2026-10-14T08:00:00Z', 'time_zone': 'Europe/Berlin'})
        self.assertEqual(preview['channels'][0]['programs'][0]['title'], '0')
        self.assertEqual(len(preview['channels'][0]['programs']), 7)
        self.assertEqual(len(payload['channels'][0]['programs']), 30)
        utc = ui.guide_preview(payload, {'at': '2026-10-14T08:00:00Z', 'time_zone': 'UTC'})
        self.assertEqual(utc['channels'][0]['programs'][0]['title'], '4')

    def test_preview_invalid_time_zone_and_timestamp_fall_back(self):
        for body in ({}, {'at': None, 'time_zone': None}, {'at': 'bad', 'time_zone': '../../bad'},
                     {'at': '2026-10-14T08:00:00', 'time_zone': 123}):
            with self.subTest(body=body):
                result = ui.guide_preview({'ui': {}, 'channels': []}, body)
                self.assertEqual(result['channels'], [])
                self.assertTrue(result['_preview'])

    def test_personal_sender_order_and_raw_alias_resolve_without_duplicates(self):
        result=ui.personal_payload(self.catalogue,self.feed,{'country':'de','channels':['extra.tv','DasErste.de','ard','zdf']})
        self.assertEqual(result['order'],['extra.tv','ard','zdf'])
        self.assertEqual(result['supported_countries'],[{'code':'de','name':'Deutschland'}])

    def test_canonical_selection_wins_over_another_stations_feed_alias(self):
        catalogue = [
            {'id': 'first', 'name': 'First', 'xmltv_id': 'second'},
            {'id': 'second', 'name': 'Second', 'xmltv_id': 'second.feed'},
        ]
        for selection, expected in [(['second'], ['second']),
                                    (['second.feed'], ['second']),
                                    (['second', 'first'], ['second', 'first'])]:
            with self.subTest(selection=selection):
                options = {'channels': selection}
                self.assertEqual(ui.personal_payload(catalogue, [], options)['order'], expected)
                self.assertEqual(ui.build_guide([], catalogue, [], options, self.at)['custom_channel_ids'], expected)

    def test_all_channel_default_and_display_bound(self):
        feed=[{'id':str(i),'name':str(i)} for i in range(400)]
        result=ui.build_guide([],[],feed,{},self.at)
        self.assertLessEqual(len(result['channels']),200)
        self.assertEqual(len(result['main_channel_ids']),200)

    def test_feed_alias_cannot_replace_the_canonical_station(self):
        catalogue=[{'id':'ard','name':'Das Erste','xmltv_id':'DasErste.de','available':True}]
        feed=[{'id':'DasErste.de','name':'Das Erste'},{'id':'ard','name':'Other feed station'}]
        records=[{**self.records[0],'channel':'DasErste.de','title':'Canonical programme'},
                 {**self.records[0],'channel':'ard','title':'Wrong programme'}]
        result=ui.build_guide(records,catalogue,feed,{'country':'de'},self.at)
        self.assertEqual(len(result['channels']),1)
        self.assertEqual(result['channels'][0]['name'],'Das Erste')
        self.assertEqual(result['channels'][0]['programs'][0]['title'],'Canonical programme')
        choices=ui.personal_payload(catalogue,feed,{'country':'de'})
        self.assertEqual(choices['order'],['ard'])
        self.assertEqual(len(choices['channels']),1)

    def test_settings_validation_rejects_invalid_writes(self):
        for values in ({'country':'bad'},{'columns_desktop':7},{'max_channels':-1},{'refresh_minutes':1},{'theme_mode':'other'},{'notification_service':'shell.execute'},{'unknown':'x'},{'columns_desktop':True}):
            with self.subTest(values=values),self.assertRaises(ValueError):ui.normalize_ui_settings(values)
        result=ui.normalize_ui_settings({'country':'de','columns_desktop':5,'refresh_minutes':60,'notification_service':'notify.mobile_app_test'})
        self.assertEqual(result['notification_service'],'notify.mobile_app_test')

    def test_visible_xmltv_limit_accepts_the_same_range_as_the_settings_menu(self):
        for value in (0, 1, 200, 300, 500):
            self.assertEqual(ui.normalize_ui_settings({'max_channels':value})['max_channels'], value)
        with self.assertRaises(ValueError):
            ui.normalize_ui_settings({'max_channels':501})

    def test_valid_existing_custom_refresh_intervals_remain_editable(self):
        for value in (30, 90, 1440):
            self.assertEqual(ui.normalize_ui_settings({'refresh_minutes':value})['refresh_minutes'], value)
        for value in (29, 1441, True, 90.5):
            with self.assertRaises(ValueError):
                ui.normalize_ui_settings({'refresh_minutes':value})

    def test_scoped_modules_and_pinned_reference_provenance(self):
        app=ROOT/'frontend'/'app'
        provenance=json.loads((app/'REFERENCE.json').read_text(encoding='utf-8'))
        for name in ('styles.css','guide-core.js','channel-picker.js','translations.js','i18n.js'):
            bundled = (app/name).read_bytes()
            original = (ROOT.parents[1]/'tests'/'reference-frontend'/name).read_bytes()
            self.assertEqual(hashlib.sha256(bundled).hexdigest(),provenance['bundled_sha256'][name],name)
            self.assertEqual(hashlib.sha256(original).hexdigest(),provenance['source_sha256'][name],name)
        logos=json.loads((app/'logo_catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(len(logos),10)
        for country in logos.values():
            for channel in country.values():
                for asset in channel.values():self.assertTrue((app/asset).is_file(),asset)

if __name__=='__main__':unittest.main()
