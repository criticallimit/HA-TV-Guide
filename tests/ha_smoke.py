"""Real HA startup, TV Guide actions, registry platforms, reload and unload smoke test.

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
import threading
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
        shutdown_scheduler = None
        try:
            configured = await async_from_config_dict({
                'homeassistant': {'name': 'TV Guide smoke', 'time_zone': 'Europe/Berlin', 'country': 'AT'},
                'http': {'server_host': '127.0.0.1', 'server_port': 8123},
                'persistent_notification': {},
                'api': {},
                'websocket_api': {},
            }, hass)
            assert configured is not None
            await hass.config.async_update(language='de')
            await hass.async_start()
            foreign_id='sensor.tv_guide_bookmark_count'
            hass.states.async_set(foreign_id,'9999',{'tv_guide_source':'criticallimit/TV-Guide'})
            from custom_components.tv_guide.guide_runtime import GuideRuntime
            with patch.object(GuideRuntime, 'start_background', lambda *args, **kwargs: None):
                result = await hass.config_entries.flow.async_init('tv_guide', context={'source':'user'})
                assert result['type'] == 'create_entry', result
                entry = result['result']
                assert entry.data['country']=='at'
                assert entry.data['language']=='de'
                assert 'backend_mode' not in entry.data
                assert 'feed_url' not in entry.data
                await hass.async_block_till_done()
                assert entry.state.value == 'loaded', entry.state
                from homeassistant.helpers import entity_registry as er
                registry = er.async_get(hass)
                assert len([item for item in registry.entities.values() if item.config_entry_id==entry.entry_id])==6
                assert not any(item.unique_id.startswith('tv_guide_bridge_') for item in registry.entities.values() if item.config_entry_id==entry.entry_id)
                bookmark_count_id=registry.async_get_entity_id('sensor','tv_guide','tv_guide_saved_bookmarks_count')
                assert hass.states.get(bookmark_count_id).state=='0'
                assert hass.states.get(foreign_id).state=='9999'
                for domain, unique_id in (
                    ('sensor', 'tv_guide_next_reminder'),
                    ('sensor', 'tv_guide_saved_bookmarks_count'),
                    ('sensor', 'tv_guide_saved_reminders_count'),
                    ('sensor', 'tv_guide_epg_last_successful_refresh'),
                    ('binary_sensor', 'tv_guide_refresh_running'),
                ):
                    entity_id = registry.async_get_entity_id(domain, 'tv_guide', unique_id)
                    assert entity_id is not None, unique_id
                    entity = registry.async_get(entity_id)
                    assert entity.config_entry_id == entry.entry_id
                    assert entity.disabled_by is None
                    assert hass.states.get(entity_id) is not None
                from homeassistant.components import frontend
                assert frontend.async_panel_exists(hass,'tv-guide')
                assert '/tv_guide/frontend/tv-guide-card.js?v=40' in hass.data[frontend.DATA_EXTRA_MODULE_URL].urls
                coordinator = hass.data['tv_guide'][entry.entry_id]
                assert coordinator._cancel_maintenance is not None
                assert coordinator.backend.settings.persistent is False
                from homeassistant.helpers.aiohttp_client import async_get_clientsession
                assert coordinator.backend.provider_client.session is async_get_clientsession(hass)
                with patch.object(coordinator.backend,'maintain_caches') as maintenance:
                    await coordinator._async_maintenance(None)
                    maintenance.assert_called_once()
                import aiohttp
                source=next(key for key in coordinator.backend._logos.entries if key.startswith('logos/europe/light/'))
                logo_cache=coordinator.backend._logos.archive_root
                logo_cache.mkdir(parents=True,exist_ok=True)
                for sample in (root/'tests/fixtures/logo-samples').glob('*.zip'):
                    shutil.copy2(sample,logo_cache/sample.name)
                progress=await hass.services.async_call('tv_guide','get_preparation_status',{},blocking=True,return_response=True)
                assert progress['logos']['total']==37
                assert progress['first_install'] is True
                async with aiohttp.ClientSession() as client:
                    async with client.get('http://127.0.0.1:8123/tv_guide/logo/'+source) as response:
                        assert response.status==200
                        assert response.headers['Content-Type'].startswith('image/svg+xml')
                        artwork=await response.read()
                        assert b'href="data:image/' in artwork
                        assert b'../assets/' not in artwork
                    async with client.get('http://127.0.0.1:8123/tv_guide/logo/not-a-logo') as response:
                        assert response.status==404
                    from zipfile import BadZipFile
                    with patch.object(coordinator.backend._logos,'render',side_effect=BadZipFile('Damaged fixture')):
                        async with client.get('http://127.0.0.1:8123/tv_guide/logo/'+source) as response:
                            assert response.status==404
                store = coordinator.backend.runtime.STORE
                now = datetime.now(timezone.utc)
                store.refresh_running = False
                store.channels[0]['programs'] = [{
                    'title':'TV Guide test programme', 'start':(now+timedelta(hours=1)).isoformat(),
                    'end':(now+timedelta(hours=2)).isoformat(), 'desc':'HA runtime fixture',
                    'icon':'https://example.org/programme.jpg',
                }]
                store.channels[0]['available'] = True
                coordinator.backend._backend_changed()
                await coordinator._async_sync()
                async def request(endpoint, method='GET', body=None):
                    return await hass.services.async_call('tv_guide','guide_request',
                        {'endpoint':endpoint,'method':method,**({'body':body} if body is not None else {})},
                        blocking=True,return_response=True)
                guide = await request('guide')
                preview = await request('guide', body={'preview': True, 'at': now.isoformat(), 'time_zone': 'UTC'})
                assert preview['_preview'] is True
                assert preview['revision'] == guide['revision']
                assert preview['channels'][0]['programs'] == guide['channels'][0]['programs']
                assert '_preview' not in (await request('guide'))
                compact=await request('guide',body={'compact':True})
                restored={key:value for key,value in compact.items() if key!='programme_sets'}
                restored['channels']=[{**{key:value for key,value in channel.items() if key!='programme_set'},
                    'programs':compact['programme_sets'][channel['programme_set']]} for channel in compact['channels']]
                assert restored == guide
                unchanged=await request('guide',body={'known_revision':guide['revision']})
                assert unchanged=={'unchanged':True,'revision':guide['revision']}
                with patch.object(coordinator.backend,'start_logo_download') as retry_logos, \
                        patch.object(coordinator,'async_guide_request',side_effect=AssertionError('Healthy EPG must not redownload')):
                    retried=await hass.services.async_call('tv_guide','retry_preparation',{},blocking=True,return_response=True)
                    retry_logos.assert_called_once_with(True)
                    assert retried['logos']['total']==37
                programme = guide['channels'][0]['programs'][0]
                assert programme['icon'].endswith('programme.jpg')
                window=await hass.services.async_call('tv_guide','get_guide',
                    {'at':now.isoformat()},blocking=True,return_response=True)
                assert window['channels'][0]['programs'][0]['id']==programme['id']
                empty_window=await hass.services.async_call('tv_guide','get_guide',
                    {'at':(now+timedelta(hours=3)).isoformat()},blocking=True,return_response=True)
                assert empty_window['channels'][0]['programs']==[]
                queried = await hass.services.async_call('tv_guide','get_programmes',
                    {'start':now.isoformat(),'end':(now+timedelta(hours=3)).isoformat(),'limit':1},
                    blocking=True,return_response=True)
                assert queried['count']==1
                assert queried['programmes'][0]['title']=='TV Guide test programme'
                calendar_id=registry.async_get_entity_id('calendar','tv_guide','tv_guide_xmltv_programmes_calendar')
                calendar_result=await hass.services.async_call('calendar','get_events',
                    {'entity_id':calendar_id,'start_date_time':now.isoformat(),'end_date_time':(now+timedelta(hours=3)).isoformat()},
                    blocking=True,return_response=True)
                assert calendar_result[calendar_id]['events'][0]['summary']=='TV Guide test programme'
                picker = await request('personal-channels')
                assert {item['code'] for item in picker['supported_countries']} == set(coordinator.backend.runtime.COUNTRIES)
                keys = [next(ch['id'] for ch in picker['channels'] if ch['id'].startswith(code+':')) for code in ('de','at')]
                await request('personal-channels','POST',{'order':keys,'countries':['de','at']})
                assert (await request('personal-channels'))['order'] == keys
                settings = await request('settings')
                await request('settings','POST',{**settings,'columns_desktop':4})
                await hass.async_block_till_done()
                assert (await request('settings'))['columns_desktop'] == 4
                # A completed old executor snapshot must not restore the old
                # country and cause an options-listener reload after a save.
                entered, release = threading.Event(), threading.Event()
                original_snapshot = coordinator.backend.state_snapshot
                first_snapshot = True
                def delayed_snapshot():
                    nonlocal first_snapshot
                    captured = original_snapshot()
                    if first_snapshot:
                        first_snapshot = False
                        entered.set()
                        if not release.wait(10):
                            raise TimeoutError('Country snapshot test was not released')
                    return captured
                catalogue_entered, catalogue_release = threading.Event(), threading.Event()
                original_catalogue = coordinator.backend.runtime.PERSONAL_CHANNELS.settings
                def delayed_catalogue(store):
                    catalogue_entered.set()
                    if not catalogue_release.wait(10):
                        raise TimeoutError('Country catalogue test was not released')
                    return original_catalogue(store)
                original_cache_load = coordinator.backend.runtime.EPGStore._load_parsed_cache
                def background_cache_load(store):
                    assert threading.current_thread().name.startswith('tv-guide-cache'), 'Settings must not restore a full cache in the HA executor'
                    return original_cache_load(store)
                with patch.object(coordinator.backend, 'state_snapshot', delayed_snapshot), \
                        patch.object(coordinator.backend.runtime.PERSONAL_CHANNELS, 'settings', delayed_catalogue), \
                        patch.object(coordinator.backend.runtime.EPGStore, '_load_parsed_cache', background_cache_load), \
                        patch.object(hass.config_entries, 'async_reload', side_effect=AssertionError('Settings must not reload the integration')) as reload_entry:
                    old_snapshot = asyncio.create_task(coordinator._snapshot())
                    old_catalogue = asyncio.create_task(request("personal-channels"))
                    try:
                        assert await asyncio.to_thread(entered.wait, 2)
                        assert await asyncio.to_thread(catalogue_entered.wait, 2)
                        for country, language in [('fr','fr'), ('de','nl'), ('gb','auto')]:
                            result = await asyncio.wait_for(request('settings', 'POST',
                                {**settings, 'columns_desktop':4, 'country':country, 'language':language}), 2)
                            assert result['ok']
                        release.set()
                        catalogue_release.set()
                        await old_catalogue
                        await old_snapshot
                        await hass.async_block_till_done()
                        assert coordinator.country == 'gb'
                        assert entry.options['country'] == 'gb'
                        assert entry.options['language'] == 'auto'
                        current = await request('guide')
                        assert current['country'] == 'gb' and current['ui']['language'] == 'auto'
                        assert hass.data['tv_guide'][entry.entry_id] is coordinator
                        reload_entry.assert_not_called()
                    finally:
                        release.set()
                        catalogue_release.set()
                        await old_catalogue
                        await old_snapshot
                await request('settings', 'POST', {**settings, 'columns_desktop':4})
                await hass.async_block_till_done()
                print('PASS HA rapid country/language changes during a delayed snapshot without reload or blocked saves', flush=True)
                fields = {'id':programme['id'],'title':programme['title'],'channel':'Das Erste','channel_id':'at:'+'x'*160,
                          'start':programme['start'],'end':programme['end']}
                await hass.services.async_call('tv_guide','save_bookmark',fields,blocking=True)
                await hass.services.async_call('tv_guide','save_reminder',{**fields,'minutes':'15'},blocking=True)
                saved = await hass.services.async_call('tv_guide','get_saved_programmes',{},blocking=True,return_response=True)
                assert len(saved['bookmarks']) == len(saved['reminders']) == 1
                assert saved['bookmarks'][0]['channelId']==fields['channel_id']
                assert saved['reminders'][0]['channelId']==fields['channel_id']
                assert saved['reminders'][0]['minutes']==15
                from homeassistant.exceptions import HomeAssistantError
                try:
                    await hass.services.async_call('tv_guide','save_reminder',
                        {**fields,'id':'invalid-utc','start':'9999-12-31T23:30:00-01:00','end':'9999-12-31T23:45:00-01:00','minutes':10},blocking=True)
                except HomeAssistantError:
                    pass
                else:
                    raise AssertionError('Unrepresentable UTC dates must not enter saved storage')
                assert len(hass.data['tv_guide_saved'][entry.entry_id].reminders)==1
                count_id=registry.async_get_entity_id('sensor','tv_guide','tv_guide_saved_reminders_count')
                assert hass.states.get(count_id).state=='1'
                guide_saved=hass.data['tv_guide_saved'][entry.entry_id]
                guide_saved.reminders[0]['sent']=True
                await guide_saved.async_save()
                assert hass.states.get(count_id).state=='0'
                guide_saved.reminders[0]['sent']=False
                await guide_saved.async_save()
                from ha_acceptance import exercise_acceptance
                await exercise_acceptance(hass, entry, coordinator)
                assert any(state.entity_id.startswith('calendar.') for state in hass.states.async_all())
                hass.config_entries.async_update_entry(entry,
                    data={**entry.data,'backend_mode':'original'},
                    options={**entry.options,'backend_mode':'old'},version=1,minor_version=1)
                await hass.async_block_till_done()
                menu_settings = {**await request('settings'), 'language':'en', 'default_view':'2015',
                                 'theme_mode':'light', 'columns_desktop':6, 'max_channels':1,
                                 'refresh_minutes':720, 'notification_service':'notify.mobile_app_menu_test'}
                await asyncio.wait_for(request('settings', 'POST', menu_settings), 2)
                menu_keys = ('country','language','default_view','theme_mode','columns_desktop',
                             'max_channels','refresh_minutes','notification_service')
                legacy_root = coordinator.backend.settings.path.parent
                def seed_legacy_storage():
                    old_frontend = legacy_root / 'reference' / 'www'
                    old_frontend.mkdir(parents=True,exist_ok=True)
                    (old_frontend / 'app.js').write_text('obsolete iframe code',encoding='utf-8')
                    (legacy_root / 'options.json').write_text('{"country":"de","language":"fr"}',encoding='utf-8')
                await hass.async_add_executor_job(seed_legacy_storage)
                for cycle in range(3):
                    previous_backend = hass.data['tv_guide'][entry.entry_id].backend
                    previous_scheduler = hass.data['tv_guide_reminder_schedulers'][entry.entry_id]
                    assert await hass.config_entries.async_reload(entry.entry_id)
                    await hass.async_block_till_done()
                    assert previous_backend.closed
                    assert previous_scheduler._stopped
                    assert entry.version==2
                    assert 'backend_mode' not in entry.data and 'backend_mode' not in entry.options
                    assert len([item for item in registry.entities.values() if item.config_entry_id==entry.entry_id])==6
                    restored_settings = await request('settings')
                    assert all(restored_settings[key] == menu_settings[key] for key in menu_keys)
                    current_coordinator = hass.data['tv_guide'][entry.entry_id]
                    assert current_coordinator.update_interval.total_seconds() == 720*60
                    def legacy_storage_removed():
                        return not (legacy_root / 'reference').exists() and not (legacy_root / 'options.json').exists()
                    assert await hass.async_add_executor_job(legacy_storage_removed)
                    assert hass.data['tv_guide_reminder_schedulers'][entry.entry_id].notification_service == menu_settings['notification_service']
                print('PASS HA complete settings persistence and runtime application through three reloads', flush=True)
                print('PASS HA acceptance: version-one migration and three reload cycles without entity duplication or surviving old workers/timers',flush=True)
                assert entry.version==2
                assert frontend.async_panel_exists(hass,'tv-guide')
                saved = await hass.services.async_call('tv_guide','get_saved_programmes',{},blocking=True,return_response=True)
                assert len(saved['bookmarks']) == len(saved['reminders']) == 1
                assert await hass.config_entries.async_unload(entry.entry_id)
                assert not hass.services.has_service('tv_guide','guide_request')
                assert not hass.data['tv_guide']
                assert not frontend.async_panel_exists(hass,'tv-guide')
                assert hass.states.get(foreign_id).state=='9999'
                # Deleting the config entry must remove only its entities and files.
                guide_storage = Path(hass.config.path('.storage','tv_guide_store',entry.entry_id))
                saved_storage = Path(hass.config.path('.storage',f'tv_guide.{entry.entry_id}.saved_programmes'))
                assert guide_storage.exists()
                assert saved_storage.exists()
                owned_ids = [entity.entity_id for entity in registry.entities.values()
                             if entity.config_entry_id == entry.entry_id]
                assert len(owned_ids) == 6
                assert await hass.config_entries.async_remove(entry.entry_id)
                await hass.async_block_till_done()
                assert not [entity for entity in registry.entities.values()
                            if entity.config_entry_id == entry.entry_id]
                assert all(hass.states.get(entity_id) is None for entity_id in owned_ids)
                assert not guide_storage.exists()
                assert not saved_storage.exists()
                assert hass.states.get(foreign_id).state == '9999'
                print(f'PASS real Home Assistant {__version__}: setup, reload, unload and complete removal of owned entities and storage',flush=True)
                # Exercise the actual HA stop event independently of entry unload.
                from custom_components.tv_guide.reminder_scheduler import TVGuideReminderScheduler
                from custom_components.tv_guide.saved_programmes import TVGuideSavedProgrammes
                shutdown_saved = TVGuideSavedProgrammes(hass, 'shutdown-regression')
                shutdown_saved.reminders = [{'id':'shutdown-regression', 'minutes':5,
                    'start':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}]
                shutdown_scheduler = TVGuideReminderScheduler(hass, shutdown_saved, asyncio.Lock())
                shutdown_scheduler.reschedule()
                assert shutdown_scheduler._cancellations
        finally:
            await hass.async_stop(force=True)
        assert shutdown_scheduler is not None and shutdown_scheduler._stopped
        assert not shutdown_scheduler._cancellations
        assert shutdown_scheduler._stop_task.done()
        print('PASS actual HA shutdown cancels reminder timers and completes scheduler cleanup', flush=True)


if __name__=='__main__':
    asyncio.run(main())
