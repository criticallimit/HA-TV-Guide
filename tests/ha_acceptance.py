"""Extended acceptance against actual HA HTTP, WebSocket, entities and timers.

Only programme-provider downloads are replaced by deterministic records. Auth,
service validation, persistence, notifications, scheduling and HA state are real.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
from homeassistant.auth.const import GROUP_ID_ADMIN


class HAClient:
    def __init__(self, socket):
        self.socket = socket
        self.sequence = 0

    async def request(self, **message):
        self.sequence += 1
        await self.socket.send_json({'id': self.sequence, **message})
        async with asyncio.timeout(15):
            while True:
                reply = await self.socket.receive_json()
                if reply.get('id') == self.sequence:
                    return reply

    async def service(self, name, data=None, *, response=True):
        reply = await self.request(type='call_service', domain='tv_guide', service=name,
                                   service_data=data or {}, return_response=response)
        assert reply['success'], (name, reply)
        return reply['result'].get('response')


async def exercise_acceptance(hass, entry, coordinator):
    now = datetime.now(timezone.utc)
    original_settings = await coordinator.async_guide_request('settings')
    original_channels = deepcopy(coordinator.backend.runtime.STORE.channels)
    original_loaded = coordinator.backend.runtime.STORE.last_loaded
    user = await hass.auth.async_create_system_user('TV Guide acceptance', group_ids=[GROUP_ID_ADMIN])
    refresh = await hass.auth.async_create_refresh_token(user)
    token = hass.auth.async_create_access_token(refresh)
    async with aiohttp.ClientSession() as session:
        async with session.get('http://127.0.0.1:8123/api/states') as response:
            assert response.status == 401
        async with session.get('http://127.0.0.1:8123/tv_guide/frontend/tv-guide-card.js') as response:
            assert response.status == 200
            assert 'tv-guide-card' in await response.text()
        async with session.ws_connect('http://127.0.0.1:8123/api/websocket') as socket:
            assert (await socket.receive_json())['type'] == 'auth_required'
            await socket.send_json({'type':'auth', 'access_token':token})
            assert (await socket.receive_json())['type'] == 'auth_ok'
            client = HAClient(socket)
            preview = await client.service('guide_request', {'endpoint':'guide', 'body':{'preview':True}})
            assert preview['_preview'] is True
            saved = await client.service('get_saved_programmes')
            assert set(saved) == {'bookmarks','reminders'}
            print('PASS HA acceptance: public assets, protected API and authenticated card WebSocket protocol', flush=True)

            # Invalid writes must fail over the same connection without changing settings.
            for data in (
                {'endpoint':'../files'},
                {'endpoint':'settings','method':'POST','body':{'country':'invalid'}},
                {'endpoint':'guide','method':'DELETE'},
            ):
                reply = await client.request(type='call_service', domain='tv_guide', service='guide_request',
                                             service_data=data, return_response=True)
                assert reply['success'] is False, data
            assert (await client.service('get_ui_settings'))['country'] == original_settings['country']
            print('PASS HA acceptance: rejected paths, methods and settings leave the connection and configuration usable', flush=True)
            valid = {'id':'invalid-input','title':'Invalid input test','channel':'Test','channel_id':'test',
                     'start':(now+timedelta(hours=1)).isoformat(),'end':(now+timedelta(hours=2)).isoformat(),'minutes':5}
            for change in ({'start':now.replace(tzinfo=None).isoformat()}, {'minutes':True},
                           {'minutes':'5.5'}, {'channel_id':'x'*201}):
                reply = await client.request(type='call_service', domain='tv_guide', service='save_reminder',
                                             service_data={**valid,**change})
                assert reply['success'] is False, change
            assert not any(r['id']=='invalid-input' for r in (await client.service('get_saved_programmes'))['reminders'])
            print('PASS HA acceptance: real service schemas reject naive dates, invalid reminder values and oversized channel IDs', flush=True)

            # Exercise every native country and default time through actual HA actions.
            country_count = 0
            for country in tuple(coordinator.backend.runtime.COUNTRIES):
                await client.service('set_ui_settings', {'options':{'country':country,'default_view':'now'}})
                store = coordinator.backend.runtime.STORE
                assert store.country == country
                store.channels = [{**channel,'programs':[]} for channel in store.channels]
                store.channels[0]['available'] = True
                store.channels[0]['programs'] = [
                    {'title':f'{country} programme {index}',
                     'start':(now-timedelta(hours=12)+timedelta(minutes=30*index)).isoformat(),
                     'end':(now-timedelta(hours=12)+timedelta(minutes=30*(index+1))).isoformat(),
                     'desc':'HA acceptance description','subtitle':'Episode','category':'Information'}
                    for index in range(96)]
                store.last_loaded = now.isoformat()
                store.refresh_running = False
                coordinator.backend._backend_changed()
                await coordinator._async_sync()
                full = await client.service('get_guide')
                assert full['country'] == country
                first = next(ch for ch in full['channels'] if ch['id'] == full['main_channel_ids'][0])
                assert len(first['programs']) == 96
                assert all(p['id'].startswith('guide_') for p in first['programs'])
                for mode in ('now','1800','2015','2200'):
                    await client.service('set_ui_settings', {'options':{'default_view':mode}})
                    for zone in ('UTC','Europe/Berlin'):
                        target = now.astimezone(ZoneInfo(zone))
                        if mode != 'now':
                            target = target.replace(hour=int(mode[:2]), minute=int(mode[2:]), second=0, microsecond=0)
                        short = await client.service('guide_request', {'endpoint':'guide','body':{
                            'preview':True,'at':now.isoformat(),'time_zone':zone}})
                        channel = next(ch for ch in short['channels'] if ch['id'] == first['id'])
                        expected = [p for p in first['programs'] if datetime.fromisoformat(p['end']) > target][:7]
                        assert channel['programs'] == expected, (country, mode, zone)
                # Day selection and calendar queries retain complete, matching data.
                target = now+timedelta(days=1)
                window = await client.service('get_guide', {'at':target.isoformat()})
                channel = next(ch for ch in window['channels'] if ch['id'] == first['id'])
                assert len(channel['programs']) == 7
                assert datetime.fromisoformat(channel['programs'][0]['end']) > target
                country_count += 1
            assert country_count == len(coordinator.backend.runtime.COUNTRIES)
            print(f'PASS HA acceptance: {country_count} registered countries, 4 time views, 2 browser time zones and next-day selection over WebSocket', flush=True)

            from custom_components.tv_guide.languages import LANGUAGES
            for language in LANGUAGES:
                await client.service('set_ui_settings', {'options':{'language':language}})
                settings=await client.service('get_ui_settings')
                assert settings['language']==language
                assert entry.options['language']==language
                guide=await client.service('get_guide')
                assert guide['ui']['language']==language
                reminder_id='registered-language-'+language
                await client.service('save_reminder',{**valid,'id':reminder_id,'language':language})
                saved_languages=await client.service('get_saved_programmes')
                assert next(item for item in saved_languages['reminders'] if item['id']==reminder_id)['language']==language
                await client.service('remove_saved_programme',{'id':reminder_id,'kind':'reminder'})
            print(f'PASS HA acceptance: all {len(LANGUAGES)} registered languages save and render through authenticated actions',flush=True)

            # Restore the original acceptance fixture before saved-item and reload tests.
            await coordinator.async_guide_request('settings', 'POST', original_settings)
            await client.service('set_ui_settings', {'options':{
                key: original_settings[key] for key in ('country','language','default_view','columns_desktop',
                    'max_channels','theme_mode','refresh_minutes','notification_service')}})
            store = coordinator.backend.runtime.STORE
            store.channels = original_channels
            store.last_loaded = original_loaded
            store.refresh_running = False
            coordinator.backend._backend_changed()
            await coordinator._async_sync()

            # A real scheduled reminder must reach HA, persist sent state, and not resend.
            reminder_id = 'ha-acceptance-due'
            delivery_now = datetime.now(timezone.utc)
            due = {'id':reminder_id,'title':'HA acceptance reminder','channel':'Acceptance channel',
                   'channel_id':'acceptance','start':(delivery_now+timedelta(minutes=4,seconds=30)).isoformat(),
                   'end':(delivery_now+timedelta(hours=1)).isoformat(),'minutes':5,'language':'de'}
            await client.service('save_reminder', due, response=False)
            async with asyncio.timeout(10):
                while True:
                    saved = await client.service('get_saved_programmes')
                    item = next((r for r in saved['reminders'] if r['id'] == reminder_id), None)
                    if item and item['sent']:
                        break
                    await asyncio.sleep(0.02)
            notifications = await client.request(type='persistent_notification/get')
            assert notifications['success']
            notification_id = 'tv_guide_'+sha256(reminder_id.encode()).hexdigest()
            notice = next(n for n in notifications['result'] if n['notification_id'] == notification_id)
            assert 'HA acceptance reminder' in notice['message']
            sent_at = item['sent_at']
            saved_file = Path(hass.config.path('.storage',f'tv_guide.{entry.entry_id}.saved_programmes'))
            persisted = json.loads(await hass.async_add_executor_job(saved_file.read_text))
            on_disk = next(r for r in persisted['data']['reminders'] if r['id']==reminder_id)
            assert on_disk['sent'] is True and on_disk['sent_at']==sent_at
            scheduler = hass.data['tv_guide_reminder_schedulers'][entry.entry_id]
            await scheduler._deliver(reminder_id)
            saved = await client.service('get_saved_programmes')
            assert next(r for r in saved['reminders'] if r['id'] == reminder_id)['sent_at'] == sent_at
            await client.service('remove_saved_programme', {'id':reminder_id,'kind':'reminder'}, response=False)
            assert not any(r['id'] == reminder_id for r in (await client.service('get_saved_programmes'))['reminders'])
            print('PASS HA acceptance: actual timer delivery, persistent notification, sent persistence and duplicate suppression', flush=True)

    duplicate = await hass.config_entries.flow.async_init('tv_guide', context={'source':'user'})
    assert duplicate['type'] == 'abort'
    assert duplicate['reason'] == 'already_configured'
    print('PASS HA acceptance: duplicate installation prevented', flush=True)
