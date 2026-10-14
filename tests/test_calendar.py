"""Calendar keeps selection and overlap semantics without per-record catalogue scans."""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import importlib.util
from pathlib import Path
import sys,types,unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components/tv_guide'
PKG='_tvguide_calendar_tests'
@dataclass
class CalendarEvent:
    start:datetime
    end:datetime
    summary:str
    description:str=''
    location:str=''
class Entity:pass
class CoordinatorEntity:
    def __init__(self,coordinator):self.coordinator=coordinator
pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT)]
ha=types.ModuleType('homeassistant.components.calendar');ha.CalendarEntity=Entity;ha.CalendarEvent=CalendarEvent
duc=types.ModuleType('homeassistant.helpers.update_coordinator');duc.CoordinatorEntity=CoordinatorEntity
with patch.dict(sys.modules,{PKG:pkg,'homeassistant.components.calendar':ha,'homeassistant.helpers.update_coordinator':duc}):
    spec=importlib.util.spec_from_file_location(PKG+'.calendar',ROOT/'calendar.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CalendarTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.coordinator=types.SimpleNamespace(data=[],canonical_channels=[{'id':'ard','xmltv_id':'ard','name':'Das Erste'},{'id':'zdf','xmltv_id':'zdf','name':'ZDF'}],channels=[])
        self.entry=types.SimpleNamespace(data={},options={})
        self.calendar=module.TVGuideProgrammeCalendar(self.coordinator,self.entry)
    def record(self,channel,begin,end,title):
        return {'channel':channel,'start':(self.now+timedelta(minutes=begin)).isoformat(),'stop':(self.now+timedelta(minutes=end)).isoformat(),'title':title}

    def test_large_snapshot_resolves_labels_once_and_keeps_earliest_event(self):
        self.coordinator.data=[self.record('ard',i+10,i+11,str(i)) for i in range(5000)]
        with patch.object(module,'channel_labels',wraps=module.channel_labels) as labels:
            event=self.calendar.event
        labels.assert_called_once()
        self.assertEqual((event.summary,event.location),('0','Das Erste'))

    def test_current_programme_selection_and_invalid_rows(self):
        self.coordinator.data=[self.record('ard',-15,-5,'ended'),self.record('ard',-5,10,'running'),self.record('zdf',3,20,'ZDF future'),{'start':'bad'}]
        self.assertEqual(self.calendar.event.summary,'running')
        self.entry.options['channels']=['zdf']
        self.assertEqual(self.calendar.event.summary,'ZDF future')

    async def test_range_overlap_and_order_preserve_names_with_one_label_scan(self):
        self.coordinator.data=[self.record('zdf',20,50,'later'),self.record('ard',-10,20,'overlap'),self.record('ard',60,90,'outside')]
        with patch.object(module,'channel_labels',wraps=module.channel_labels) as labels:
            events=await self.calendar.async_get_events(None,self.now,self.now+timedelta(minutes=30))
        labels.assert_called_once()
        self.assertEqual([event.summary for event in events],['overlap','later'])
        self.assertEqual([event.location for event in events],['Das Erste','ZDF'])
