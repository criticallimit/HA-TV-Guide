"""Authenticated response actions backing the TV Guide presentation."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .catalogs import resolve_catalogue_channels
from .ui_payload import build_guide, guide_at, personal_payload, ui_settings, normalize_ui_settings

SERVICES=('get_guide','get_personal_channels','get_ui_settings','set_ui_settings')
PRESENTATION_OPTIONS=('country','language','default_view','columns_desktop','max_channels','theme_mode','refresh_minutes','notification_service')

def async_register_ui_services(hass):
    def entry_and_options():
        stores=hass.data.get(DOMAIN+'_saved',{})
        if len(stores)!=1:
            raise HomeAssistantError('Exactly one TV Guide entry must be loaded')
        entry=hass.config_entries.async_get_entry(next(iter(stores)))
        if entry is None:
            raise HomeAssistantError('TV Guide entry not found')
        return entry,{**entry.data,**entry.options}

    async def snapshot(options):
        coordinator=next(iter(hass.data.get(DOMAIN,{}).values()),None)
        if coordinator is not None:
            return coordinator.data or [],coordinator.canonical_channels,coordinator.channels,coordinator.refresh_running
        catalogue=await hass.async_add_executor_job(resolve_catalogue_channels,options.get('country',''),[])
        return [],catalogue,[],False

    async def persist_guide_settings(entry, coordinator):
        settings=await coordinator.async_guide_request('settings')
        changes={key:settings[key] for key in PRESENTATION_OPTIONS}
        hass.config_entries.async_update_entry(entry,options={**entry.options,**changes,'backend_mode':'original'})
        scheduler=hass.data.get(DOMAIN+'_reminder_schedulers',{}).get(entry.entry_id)
        if scheduler is not None:
            scheduler.notification_service=settings['notification_service']

    async def handle(call):
        entry,options=entry_and_options()
        coordinator=hass.data.get(DOMAIN,{}).get(entry.entry_id)
        requested_at = None
        if call.service == 'get_guide' and call.data.get('at'):
            try:
                requested_at = datetime.fromisoformat(call.data['at'])
                if requested_at.tzinfo is None:
                    raise ValueError('Timestamp must include a timezone')
                requested_at.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError) as exc:
                raise HomeAssistantError('Invalid guide timestamp') from exc
        if getattr(coordinator,'is_multi_source',False):
            if call.service=='guide_request':
                try:
                    if call.data['endpoint']=='settings' and call.data.get('method')=='POST':
                        normalize_ui_settings({'notification_service':(call.data.get('body') or {}).get('notification_service','persistent_notification.create')})
                    result=await coordinator.async_guide_request(call.data['endpoint'],call.data.get('method','GET'),call.data.get('body'))
                except (ValueError,RuntimeError) as exc:
                    raise HomeAssistantError(str(exc)) from exc
                if call.service=='guide_request' and call.data['endpoint']=='settings' and call.data.get('method')=='POST':

                    await persist_guide_settings(entry, coordinator)
                return result
            endpoint={'get_ui_settings':'settings','get_guide':'guide','get_personal_channels':'personal-channels'}.get(call.service)
            if endpoint:
                result=await coordinator.async_guide_request(endpoint)
                if endpoint == 'guide' and requested_at is not None:
                    return await hass.async_add_executor_job(guide_at, result, requested_at)
                return result
            if call.service=='set_ui_settings':
                try:
                    if set(call.data['options'])-set(PRESENTATION_OPTIONS):
                        raise ValueError('Unknown settings')
                    settings=await coordinator.async_guide_request('settings')
                    normalize_ui_settings({'notification_service':call.data['options'].get('notification_service',settings['notification_service'])})
                    result=await coordinator.async_guide_request('settings','POST',{**settings,**call.data['options']})
                    await persist_guide_settings(entry, coordinator)
                except (ValueError,RuntimeError,TypeError) as exc:
                    raise HomeAssistantError(str(exc)) from exc
                return result
        if call.service=='get_ui_settings':
            return ui_settings(options)
        if call.service=='set_ui_settings':
            try:
                changes=normalize_ui_settings(call.data['options'])
            except (ValueError,TypeError) as exc:
                raise HomeAssistantError(str(exc)) from exc
            hass.config_entries.async_update_entry(entry,options={**entry.options,**changes})
            return {'ok':True,'settings':ui_settings({**options,**changes})}
        data,catalogue,channels,busy=await snapshot(options)
        if call.service=='get_personal_channels':
            return await hass.async_add_executor_job(personal_payload,catalogue,channels,options)
        raw=call.data.get('at')
        try:
            at=datetime.fromisoformat(raw) if raw else datetime.now(timezone.utc)
            if at.tzinfo is None:
                raise ValueError('Timestamp must include a timezone')
            at.astimezone(timezone.utc)
        except (TypeError,ValueError,OverflowError) as exc:
            raise HomeAssistantError('Invalid guide timestamp') from exc
        if not raw and options.get('default_view','now')!='now':
            view=options['default_view'];at=at.astimezone(ZoneInfo(hass.config.time_zone)).replace(hour=int(view[:2]),minute=int(view[2:]),second=0,microsecond=0)
        return await hass.async_add_executor_job(build_guide,data,catalogue,channels,options,at,busy)

    for service in SERVICES:
        schema=vol.Schema({vol.Optional('at'):str}) if service=='get_guide' else vol.Schema({vol.Required('options'):dict}) if service=='set_ui_settings' else vol.Schema({})
        hass.services.async_register(DOMAIN,service,handle,schema=schema,supports_response=SupportsResponse.ONLY)
    if any(getattr(item,'is_multi_source',False) for item in hass.data.get(DOMAIN,{}).values()):
        hass.services.async_register(DOMAIN,'guide_request',handle,
            schema=vol.Schema({vol.Required('endpoint'):str,vol.Optional('method',default='GET'):vol.In(['GET','POST']),vol.Optional('body'):dict}),
            supports_response=SupportsResponse.ONLY)

def async_remove_ui_services(hass):
    hass.services.async_remove(DOMAIN,'guide_request')
    for service in SERVICES:
        hass.services.async_remove(DOMAIN,service)
