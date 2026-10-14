"""Real HA startup, native actions, registry platforms, reload and unload smoke test.

Run in the official Home Assistant image. Only provider downloads are replaced
with deterministic programme data; the HA runtime and integration are real.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.const import __version__
from homeassistant.core import HomeAssistant


async def main():
    logging.basicConfig(level=logging.INFO)
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as folder:
        shutil.copytree(root / 'custom_components', Path(folder) / 'custom_components', ignore=shutil.ignore_patterns('__pycache__'))
        sys.path.insert(0, folder)
        hass = HomeAssistant(folder)
        loader.async_setup(hass)
        hass.config.skip_pip = True
        try:
            configured = await async_from_config_dict({
                'homeassistant': {'name': 'TV Guide smoke', 'time_zone': 'Europe/Berlin', 'country': 'AT'},
                'http': {'server_host': '127.0.0.1', 'server_port': 8123},
                'persistent_notification': {},
            }, hass)
            assert configured is not None
            await hass.config.async_update(language='de')
            await hass.async_start()
            foreign_id='sensor.tv_guide_bookmark_count'
            hass.states.async_set(foreign_id,'9999',{'tv_guide_source':'criticallimit/TV-Guide'})
            from custom_components.tv_guide.original_runtime import OriginalRuntime
            with patch.object(OriginalRuntime, 'start_background', lambda *args, **kwargs: None):
                result = await hass.config_entries.flow.async_init('tv_guide', context={'source':'user'})
                assert result['type'] == 'create_entry', result
                entry = result['result']
                assert entry.data['country']=='at'
                assert entry.data['language']=='de'
                assert 'feed_url' not in entry.data
                await hass.async_block_till_done()
                assert entry.state.value == 'loaded', entry.state
                from homeassistant.helpers import entity_registry as er
                registry = er.async_get(hass)
                assert len([item for item in registry.entities.values() if item.config_entry_id==entry.entry_id])==8
                assert not any(item.unique_id.startswith('tv_guide_bridge_') for item in registry.entities.values() if item.config_entry_id==entry.entry_id)
                bookmark_count_id=registry.async_get_entity_id('sensor','tv_guide','tv_guide_native_saved_bookmarks_count')
                assert hass.states.get(bookmark_count_id).state=='0'
                assert hass.states.get(foreign_id).state=='9999'
                for domain, unique_id in (
                    ('sensor', 'tv_guide_native_next_reminder'),
                    ('sensor', 'tv_guide_native_saved_bookmarks_count'),
                    ('sensor', 'tv_guide_native_saved_reminders_count'),
                    ('sensor', 'tv_guide_native_epg_last_successful_refresh'),
                    ('binary_sensor', 'tv_guide_native_refresh_running'),
                ):
                    entity_id = registry.async_get_entity_id(domain, 'tv_guide', unique_id)
                    assert entity_id is not None, unique_id
                    entity = registry.async_get(entity_id)
                    assert entity.config_entry_id == entry.entry_id
                    assert entity.disabled_by is None
                    assert hass.states.get(entity_id) is not None
                from homeassistant.components import frontend
                assert frontend.async_panel_exists(hass,'tv-guide-native')
                assert '/tv_guide/frontend/tv-guide-native-card.js?v=6' in hass.data[frontend.DATA_EXTRA_MODULE_URL].urls
                coordinator = hass.data['tv_guide'][entry.entry_id]
                assert coordinator._cancel_preload is not None
                with patch.object(coordinator.backend,'maintain_caches') as maintenance:
                    await coordinator._async_preload(None)
                    maintenance.assert_called_once()
                import aiohttp
                source=next(key for key in coordinator.backend._logos.entries if key.startswith('logos/europe/light/'))
                async with aiohttp.ClientSession() as client:
                    async with client.get('http://127.0.0.1:8123/tv_guide/logo/'+source) as response:
                        assert response.status==200
                        assert response.headers['Content-Type'].startswith('image/svg+xml')
                        artwork=await response.read()
                        assert b'href="data:image/' in artwork
                        assert b'../assets/' not in artwork
                    async with client.get('http://127.0.0.1:8123/tv_guide/logo/not-a-logo') as response:
                        assert response.status==404
                store = coordinator.backend.runtime.STORE
                now = datetime.now(timezone.utc)
                store.refresh_running = False
                store.channels[0]['programs'] = [{
                    'title':'Native HA test programme', 'start':(now+timedelta(hours=1)).isoformat(),
                    'end':(now+timedelta(hours=2)).isoformat(), 'desc':'HA runtime fixture',
                    'icon':'https://example.org/programme.jpg',
                }]
                store.channels[0]['available'] = True
                await coordinator._async_sync()
                async def request(endpoint, method='GET', body=None):
                    return await hass.services.async_call('tv_guide','native_request',
                        {'endpoint':endpoint,'method':method,**({'body':body} if body is not None else {})},
                        blocking=True,return_response=True)
                guide = await request('guide')
                programme = guide['channels'][0]['programs'][0]
                assert programme['icon'].endswith('programme.jpg')
                picker = await request('personal-channels')
                assert len(picker['supported_countries']) == 10
                keys = [next(ch['id'] for ch in picker['channels'] if ch['id'].startswith(code+':')) for code in ('de','at')]
                await request('personal-channels','POST',{'order':keys,'countries':['de','at']})
                assert (await request('personal-channels'))['order'] == keys
                settings = await request('settings')
                await request('settings','POST',{**settings,'columns_desktop':4})
                await hass.async_block_till_done()
                assert (await request('settings'))['columns_desktop'] == 4
                fields = {'id':programme['id'],'title':programme['title'],'channel':'Das Erste','channel_id':'ard',
                          'start':programme['start'],'end':programme['end']}
                await hass.services.async_call('tv_guide','save_bookmark',fields,blocking=True)
                await hass.services.async_call('tv_guide','save_reminder',{**fields,'minutes':10},blocking=True)
                saved = await hass.services.async_call('tv_guide','get_saved_programmes',{},blocking=True,return_response=True)
                assert len(saved['bookmarks']) == len(saved['reminders']) == 1
                count_id=registry.async_get_entity_id('sensor','tv_guide','tv_guide_native_saved_reminders_count')
                assert hass.states.get(count_id).state=='1'
                native_saved=hass.data['tv_guide_saved'][entry.entry_id]
                native_saved.reminders[0]['sent']=True
                await native_saved.async_save()
                assert hass.states.get(count_id).state=='0'
                native_saved.reminders[0]['sent']=False
                await native_saved.async_save()
                assert any(state.entity_id.startswith('calendar.') for state in hass.states.async_all())
                hass.config_entries.async_update_entry(entry,version=1)
                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                assert entry.version==2
                assert frontend.async_panel_exists(hass,'tv-guide-native')
                saved = await hass.services.async_call('tv_guide','get_saved_programmes',{},blocking=True,return_response=True)
                assert len(saved['bookmarks']) == len(saved['reminders']) == 1
                assert await hass.config_entries.async_unload(entry.entry_id)
                assert not hass.services.has_service('tv_guide','native_request')
                assert not hass.data['tv_guide']
                assert not frontend.async_panel_exists(hass,'tv-guide-native')
                assert hass.states.get(foreign_id).state=='9999'
                print(f'PASS real Home Assistant {__version__}: setup, platforms, full guide, country picker, settings, saved actions, reload, unload',flush=True)
        finally:
            await hass.async_stop(force=True)


if __name__=='__main__':
    asyncio.run(main())
