"""Native sensor switches affect only the integration's own registry entries."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components'/'tv_guide'
PKG='_tvguide_sensor_controls_tests'


class SensorControlTests(unittest.TestCase):
    def setUp(self):
        pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT)]
        spec=importlib.util.spec_from_file_location(PKG+'.sensor_controls',ROOT/'sensor_controls.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{PKG:pkg}):spec.loader.exec_module(self.module)
        self.entities={uid:types.SimpleNamespace(entity_id=domain+'.'+uid,config_entry_id='entry',disabled_by=None)
            for domain,uid in self.module.NATIVE_SENSORS.values()}
        self.writes=[]
        def update(entity_id,**changes):
            self.writes.append(entity_id)
            for entity in self.entities.values():
                if entity.entity_id==entity_id:entity.disabled_by=changes['disabled_by']
        registry=types.SimpleNamespace(async_get_entity_id=lambda domain,platform,uid:self.entities[uid].entity_id if uid in self.entities else None,
            async_get=lambda eid:next((entry for entry in self.entities.values() if entry.entity_id==eid),None),async_update_entity=update)
        er=types.SimpleNamespace(async_get=lambda hass:registry,RegistryEntryDisabler=types.SimpleNamespace(USER='user'))
        helpers=types.ModuleType('homeassistant.helpers');helpers.entity_registry=er
        self.patch=patch.dict(sys.modules,{'homeassistant.helpers':helpers});self.patch.start();self.addCleanup(self.patch.stop)

    def test_enabled_flags_and_toggle_roundtrip(self):
        self.assertTrue(all(self.module.sensor_settings(None,'entry').values()))
        self.module.set_sensor_settings(None,'entry',{'sensor_bookmark_count':False})
        self.assertFalse(self.module.sensor_settings(None,'entry')['sensor_bookmark_count'])
        self.module.set_sensor_settings(None,'entry',{'sensor_bookmark_count':True})
        self.assertTrue(self.module.sensor_settings(None,'entry')['sensor_bookmark_count'])
        self.assertEqual(len(self.writes),2)

    def test_invalid_flags_and_other_entry_cannot_be_changed(self):
        with self.assertRaises(ValueError):self.module.set_sensor_settings(None,'entry',{'sensor_bookmark_count':'false'})
        self.module.set_sensor_settings(None,'other',{'sensor_bookmark_count':False})
        self.assertEqual(self.writes,[])


if __name__=='__main__':unittest.main()
