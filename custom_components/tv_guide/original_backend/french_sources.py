"""Public French broadcaster schedules, isolated from the other country parsers."""
import html
import json
import re
from datetime import timedelta
from zoneinfo import ZoneInfo


def flight_text(page):
    chunks = []
    for block in re.findall(r'self\.__next_f\.push\((\[.*?\])\)</script>', page, re.S):
        try:
            value = json.loads(block)
            if len(value) > 1 and value[0] == 1 and isinstance(value[1], str):
                chunks.append(value[1])
        except (ValueError, TypeError):
            continue
    return ''.join(chunks)


def plain_text(value):
    return html.unescape(re.sub(r'<[^>]+>', '', value or '')).strip()


class FrenchProgrammeSources:
    def _french_m6(self, page, marker, day):
        match = re.search(r'root\.__dehydratedState\s*=\s*', page)
        if not match:
            return []
        state, _ = json.JSONDecoder().raw_decode(page, match.end())
        state = json.loads(state['__reduxState'])
        rows = state.get('epg', {}).get('programByDateByChannel', {}).get(marker, {}).get(day.isoformat(), [])
        result = []
        zone = ZoneInfo('Europe/Paris')
        for row in rows:
            try:
                if row.get('channel', {}).get('code') != marker:
                    continue
                start = self.runtime.datetime.fromisoformat(row['diffusion_start_date'])
                end = self.runtime.datetime.fromisoformat(row['diffusion_end_date'])
                start = start.replace(tzinfo=zone) if start.utcoffset() is None else start.astimezone(zone)
                end = end.replace(tzinfo=zone) if end.utcoffset() is None else end.astimezone(zone)
                if start.date() != day or not start < end <= start + timedelta(days=1):
                    continue
                # The programme title is the series; the video title can be an episode.
                result.append({'title': (row.get('program') or {}).get('title') or row.get('title'),
                               'subtitle': row.get('subtitle') or '', 'desc': row.get('description') or '',
                               'start_dt': start, 'end_dt': end})
            except (KeyError, ValueError, TypeError):
                continue
        return result

    def _french_tf1(self, page, marker):
        result = []

        def visit(value):
            if isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, dict):
                if value.get('slug') == marker and isinstance(value.get('live'), dict):
                    for key in ('live', 'next', 'tonight'):
                        row = value.get(key)
                        if not isinstance(row, dict):
                            continue
                        try:
                            start = self.runtime.datetime.fromisoformat(row['startAt'])
                            end = self.runtime.datetime.fromisoformat(row['endAt'])
                            if start.utcoffset() is None or end.utcoffset() is None:
                                continue
                            label = row.get('decoration', {}).get('programLabel') or row.get('title')
                            result.append({'title': label,
                                           'subtitle': row.get('title') if row.get('title') != label else '',
                                           'start_dt': start, 'end_dt': end})
                        except (KeyError, ValueError, TypeError):
                            continue
                for child in value.values():
                    if isinstance(child, (dict, list)):
                        visit(child)

        for line in flight_text(page).splitlines():
            _, _, payload = line.partition(':')
            if payload.startswith(('{', '[')):
                try:
                    visit(json.loads(payload))
                except ValueError:
                    continue
        return result

    def _french_ftv(self, page, marker):
        # Weekly grids have repeated featured entries; deduplicate by exact start.
        canonical = re.search(r'<link\b[^>]*rel="canonical"[^>]*href="([^"]+)"', page)
        if not canonical or not canonical[1].startswith(f'https://www.francetvpro.fr/grille/{marker}/'):
            return []
        result = {}
        pattern = r'<time\b[^>]*datetime="([^"]+)"[^>]*>.*?</time>(.*?class="program-item__name"[^>]*>)(.*?)</a>'
        for start_text, _, title in re.findall(pattern, page, re.S):
            try:
                start = self.runtime.datetime.fromisoformat(start_text)
                if start.utcoffset() is not None:
                    result[start] = {'title': plain_text(title), 'start_dt': start}
            except ValueError:
                continue
        return list(result.values())

    def _french_arte(self, page, day):
        canonical = re.search(r'<link\b[^>]*rel="canonical"[^>]*href="([^"]+)"', page)
        if not canonical or canonical[1] != f'https://www.arte.tv/fr/guide/{day:%Y%m%d}/':
            return []
        result = []
        current_day = day
        previous = None
        for block in re.findall(r'<li\b[^>]*data-testid="tsguide-itm"[^>]*>(.*?)</li>', page, re.S):
            time = re.search(r'>(\d{2}):(\d{2})</span>', block)
            title = re.search(r'<h3\b[^>]*data-testid="ts-tsTitle"[^>]*>(.*?)</h3>', block, re.S)
            subtitle = re.search(r'<p\b[^>]*data-testid="ts-tsSubtitle"[^>]*>(.*?)</p>', block, re.S)
            if not time or not title:
                continue
            minutes = int(time[1]) * 60 + int(time[2])
            if previous is not None and minutes < previous:
                current_day += timedelta(days=1)
            previous = minutes
            start = self.runtime.datetime.combine(current_day, self.runtime.datetime.min.time(), ZoneInfo('Europe/Paris'))
            result.append({'title': plain_text(title[1]), 'subtitle': plain_text(subtitle[1]) if subtitle else '',
                           'start_dt': start + timedelta(minutes=minutes)})
        return result

    def _fetch_french_programs(self, provider):
        today = self.runtime.datetime.now(ZoneInfo('Europe/Paris')).date()
        kind = provider['kind']
        raw = []
        for offset in range(1 if kind == 'fr_tf1' else 4 if kind == 'fr_arte' else 3):
            day = today + timedelta(days=offset)
            suffix = '' if offset == 0 else f'/dans-{offset}j'
            url = provider['url'].format(date=day.isoformat(), compact=day.strftime('%Y%m%d'),
                                         french=day.strftime('%d-%m-%Y'), suffix=suffix)
            try:
                page = self._fetch_html(url, provider['marker'])
                if kind == 'fr_m6':
                    rows = self._french_m6(page, provider['marker'], day)
                elif kind == 'fr_tf1':
                    rows = self._french_tf1(page, provider['marker'])
                elif kind == 'fr_ftv':
                    rows = self._french_ftv(page, provider['marker'])
                else:
                    rows = self._french_arte(page, day)
                raw.extend({**row, '_source_url': url} for row in rows if row.get('title'))
                if kind == 'fr_ftv':
                    covered = {row['start_dt'].astimezone(ZoneInfo('Europe/Paris')).date() for row in raw}
                    if all(today + timedelta(days=n) in covered for n in range(3)):
                        break  # Fetch the next weekly grid when the preview crosses a week boundary.
            except (KeyError, ValueError, TypeError, OSError) as exc:
                print(f'[TV Guide] Französische Programmquelle {provider["marker"]}: {exc}', flush=True)
        ordered = sorted({row['start_dt']: row for row in raw}.values(), key=lambda row: row['start_dt'])
        valid = []
        for index, row in enumerate(ordered):
            start = row['start_dt'].astimezone(ZoneInfo('Europe/Paris'))
            end = row.get('end_dt')
            if end is None and index + 1 < len(ordered):
                end = ordered[index + 1]['start_dt']
            # Never fabricate an end for the last programme or across a large gap.
            if end is None or not start < end <= start + timedelta(hours=12):
                continue
            if not today <= start.date() < today + timedelta(days=3):
                continue
            valid.append({**row, 'start_dt': start.astimezone(self.runtime.EPG_TIMEZONE),
                          'end_dt': end.astimezone(self.runtime.EPG_TIMEZONE)})
        programmes = self._build_programmes_from_starts(valid)
        for programme, row in zip(programmes, valid):
            programme['end'] = row['end_dt'].isoformat()
            programme['_source_url'] = row['_source_url']
        return programmes
