"""Automatic HA locale and no-input config flow tests."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components'/'tv_guide'
PKG='_tvguide_setup_tests'
package=types.ModuleType(PKG);package.__path__=[str(ROOT)]


class Flow:
    def __init_subclass__(cls,**kwargs):pass
    async def async_set_unique_id(self,value):self.unique_id=value
    def _abort_if_unique_id_configured(self):pass
    def async_create_entry(self,**values):return {'type':'create_entry',**values}
    def async_show_form(self,**kwargs):raise AssertionError('No input form should be shown')


class DefaultsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ha=types.ModuleType('homeassistant');ha.config_entries=types.SimpleNamespace(ConfigFlow=Flow)
        with patch.dict(sys.modules,{PKG:package,'homeassistant':ha}):
            for name in ('const','country_sources','ha_defaults','config_flow'):
                spec=importlib.util.spec_from_file_location(PKG+'.'+name,ROOT/(name+'.py'))
                module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
                if name=='ha_defaults':self.defaults=module.installation_defaults
            self.flow=module.TVGuideConfigFlow

    async def test_country_and_language_use_independent_ha_settings(self):
        result=self.defaults(types.SimpleNamespace(country='CH',language='fr-CH'))
        self.assertEqual((result['country'],result['language']),('ch','fr'))
        self.assertNotIn('backend_mode',result)
        self.assertNotIn('feed_url',result)

    async def test_missing_and_unsupported_locale_never_require_a_question(self):
        self.assertEqual(self.defaults(types.SimpleNamespace(country=None,language='no_NO'))['country'],'no')
        self.assertEqual(self.defaults(types.SimpleNamespace(country='US',language='en-US'))['country'],'gb')
        self.assertEqual(self.defaults(types.SimpleNamespace(country='AT',language='unsupported'))['country'],'at')
        self.assertEqual(self.defaults(types.SimpleNamespace(country='UK',language='en'))['country'],'gb')

    async def test_first_install_independent_country_and_language(self):
        for country, language, expected in [
            ('DE', 'en', ('de', 'en')),
            ('AT', 'de', ('at', 'de')),
            ('CH', 'fr', ('ch', 'fr')),
            ('NL', 'de', ('nl', 'de')),
            ('GB', 'en', ('gb', 'en')),
        ]:
            with self.subTest(country=country, language=language):
                flow=self.flow()
                flow.hass=types.SimpleNamespace(config=types.SimpleNamespace(country=country, language=language))
                result=await flow.async_step_user()
                self.assertEqual((result['data']['country'],result['data']['language']),expected)

    async def test_first_selection_creates_entry_without_inputs(self):
        flow=self.flow();flow.hass=types.SimpleNamespace(config=types.SimpleNamespace(country='NL',language='nl'))
        result=await flow.async_step_user()
        self.assertEqual(result['type'],'create_entry')
        self.assertEqual(result['data']['country'],'nl')
        self.assertEqual(result['data']['language'],'nl')
        self.assertFalse(hasattr(flow,'async_get_options_flow'))


if __name__=='__main__':unittest.main()
