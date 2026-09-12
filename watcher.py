#!/usr/bin/env python3
"""One-shot public signal monitor. Standard library only; never logs request secrets."""
import argparse
import copy
import datetime as dt
import email.utils
import fcntl
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

SOURCE = 'https://savemetibo.com/status.json'
ENDPOINT = 'https://api.day.app/push'
LIMIT = 2097152
TITLES = {'watch': '重置线索（待确认）', 'confirmed': '社区源已确认重置',
          'landed': '社区源报告已落地', 'cooled': '本次观察已结束',
          'closed': '本次观察已结束', 'retracted': '撤回／更正',
          'corrected': '撤回／更正', 'withdrawn': '撤回／更正'}
CORRECTIONS = {'retracted', 'corrected', 'withdrawn'}
RANK = {'watch': 1, 'confirmed': 2, 'landed': 3, 'cooled': 4, 'closed': 4,
        'retracted': 5, 'corrected': 5, 'withdrawn': 5}

class Fault(Exception):
    def __init__(self, reason, retry=300):
        self.reason, self.retry = reason, retry
        super().__init__(reason)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def stamp(value, now):
    if not isinstance(value, str):
        raise Fault('invalid_time')
    try:
        d = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if d.tzinfo is None:
            raise ValueError()
        t = d.timestamp()
        if t > now + 300:
            raise ValueError()
        return t
    except (ValueError, OverflowError):
        raise Fault('invalid_time') from None

def norm(text):
    if not isinstance(text, str):
        raise Fault('invalid_text')
    return ' '.join(text.split())

def url(value):
    if not isinstance(value, str) or len(value) > 512:
        return ''
    try:
        p = urllib.parse.urlsplit(value)
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            return ''
        host = p.hostname
        if host not in ('savemetibo.com', 'x.com', 'twitter.com', 'status.openai.com'):
            return ''
        host = 'x.com' if host == 'twitter.com' else host
        return urllib.parse.urlunsplit(('https', host, p.path.rstrip('/') or '/', '', ''))
    except ValueError:
        return ''

def direct(u):
    return bool(re.fullmatch(r'https://x\.com/thsottiaux/status/\d+', u))

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def retry_after(value, now):
    try:
        return max(0, int(value))
    except (ValueError, TypeError):
        try:
            return max(0, email.utils.parsedate_to_datetime(value).timestamp() - now)
        except (ValueError, TypeError, AttributeError):
            return 0

def request(target, payload=None):
    req = urllib.request.Request(target, data=payload,
        headers={'User-Agent': 'tibo-watch/1.0', 'Accept': 'application/json',
                 'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=10) as r:
            body = r.read(LIMIT + 1)
            if len(body) > LIMIT:
                raise Fault('response_too_large')
            if r.status != 200:
                raise Fault('http_' + str(r.status))
            try:
                return json.loads(body)
            except (ValueError, UnicodeError):
                raise Fault('invalid_json') from None
    except urllib.error.HTTPError as e:
        delay = max(retry_after(e.headers.get('Retry-After'), time.time()),
                    86400 if e.code in (401, 403) and payload else 300)
        raise Fault('http_' + str(e.code), delay) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Fault('network_error') from None

def parse(data, now, previous):
    try:
        if not isinstance(data, dict) or str(data['schema_version']).split('.')[0] != '1':
            raise Fault('schema_incompatible')
        events, fresh, provider = data['events'], data['freshness'], data['providers']['codex']
        if not isinstance(events, list) or not isinstance(fresh, dict) or not isinstance(provider, dict):
            raise Fault('schema_incompatible')
        generated = stamp(data['generated_at'], now)
        checked = stamp(fresh['last_checked_at'], now)
        for field in ('stale', 'outage'):
            if type(fresh[field]) is not bool:
                raise Fault('schema_incompatible')
        if type(provider['stale']) is not bool:
            raise Fault('schema_incompatible')
        if generated < previous.get('generated', 0) or checked < previous.get('checked', 0):
            raise Fault('response_regressed')
        if not events and previous.get('had_events'):
            raise Fault('unexpected_empty_events')
        age = now - min(generated, checked)
        if age > 1800 or fresh['stale'] or fresh['outage'] or provider['stale']:
            raise Fault('source_outage' if age > 3600 or fresh['outage'] else 'source_stale')
        items, bad = [], 0
        for e in events:
            try:
                if not isinstance(e, dict):
                    raise Fault('invalid_event')
                if not isinstance(e.get('provider'), str):
                    raise Fault('invalid_event')
                if e.get('provider') != 'codex':
                    continue
                eid, state, kind = e['event_id'], e['state'], e['kind']
                if not all(isinstance(x, str) and x for x in (eid, state, kind)) or state not in TITLES:
                    raise Fault('invalid_event')
                updated = stamp(e['updated_at'], now)
                stamp(e['first_published_at'], now)
                receipts = e.get('receipt_urls', [])
                if not isinstance(receipts, list):
                    raise Fault('invalid_event')
                links = sorted(set(filter(None, (url(u) for u in receipts))))
                correction = e.get('correction_of')
                if correction is not None and not isinstance(correction, str):
                    raise Fault('invalid_event')
                item = dict(id=eid, state=state, kind=kind, headline=norm(e['headline']),
                            links=links, correction=correction, updated=updated,
                            event_url=url(e.get('event_url')), direct=any(map(direct, links)))
                items.append(item)
            except (Fault, KeyError, TypeError, ValueError):
                bad += 1
        changes = data.get('change_log', [])
        if not isinstance(changes, list):
            raise Fault('invalid_change_log')
        for c in changes:
            try:
                if not isinstance(c, dict):
                    raise Fault('invalid_change')
                if c.get('provider', 'codex') != 'codex' or c.get('category') != 'team_hint':
                    continue
                text = norm(c['text'])
                if not re.search(r'\b(reset|banked|quota|usage|limits?|allowance)\b', text, re.I):
                    continue
                u = url(c.get('event_url'))
                updated = stamp(c['at'], now)
                items.append(dict(id='hint:' + digest([u, text.casefold()]), state='watch',
                    kind='team_hint', headline=text, links=[], correction=None,
                    updated=updated, event_url=u, direct=False))
            except (Fault, KeyError, TypeError):
                bad += 1
        # Deterministic grouping by ID, event URL and reliable evidence links.
        groups = []
        for item in sorted(items, key=lambda x: (x['updated'], RANK[x['state']], x['id'])):
            keys = {item['id']} | set(item['links']) | ({item['event_url']} if item['event_url'] else set())
            matching = [g for g in groups if g[0] & keys]
            members = [item]
            for g in matching:
                keys |= g[0]; members += g[1]; groups.remove(g)
            groups.append((keys, members))
        result = []
        for _, members in groups:
            canonical = [m for m in members if m['kind'] != 'team_hint']
            item = max(canonical or members, key=lambda x: (x['updated'], RANK[x['state']], x['id']))
            item['aliases'] = sorted({m['id'] for m in (canonical or members)})
            if canonical:
                item['linked_hints'] = [m for m in members if m['kind'] == 'team_hint']
            item['semantic'] = digest(['SaveMeTibo', item['id'], item['state'], item['kind'],
                item['headline'].casefold(), item['links'], item['correction']])
            result.append(item)
        if events and not items and bad:
            raise Fault('all_events_invalid')
        return result, dict(generated=generated, checked=checked, had_events=bool(events), bad_entries=bad)
    except (KeyError, TypeError, AttributeError):
        raise Fault('schema_incompatible') from None

def blank():
    return dict(version=1, initialized=False, observed={}, accepted={}, pending={}, health={}, source={})

class State:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'state.json'
        self.backup = self.directory / 'state.backup.json'
        self.recovered = False

    def __enter__(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = open(self.directory / 'state.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise Fault('already_running') from None
        return self

    def __exit__(self, *args):
        self.lock.close()

    def load(self):
        for path in (self.path, self.backup):
            try:
                data = json.loads(path.read_text())
                if data['version'] != 1 or type(data['initialized']) is not bool:
                    raise ValueError()
                for k in ('observed', 'accepted', 'pending', 'health', 'source'):
                    if not isinstance(data[k], dict):
                        raise ValueError()
                self.recovered = path == self.backup
                return data
            except (OSError, ValueError, KeyError, TypeError):
                continue
        if self.path.exists() or self.backup.exists() or (self.directory / 'initialized').exists():
            raise Fault('state_corrupt_manual_recovery_required')
        return blank()

    def atomic(self, path, content):
        fd, temp = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content); f.flush(); os.fsync(f.fileno())
            os.replace(temp, path)
            d = os.open(self.directory, os.O_DIRECTORY)
            try: os.fsync(d)
            finally: os.close(d)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def save(self, data):
        # Backup a validated current state, never a corrupt primary.
        if self.path.exists() and not self.recovered:
            try:
                current = self.path.read_text(); json.loads(current)
                self.atomic(self.backup, current)
            except (ValueError, OSError):
                pass
        content = json.dumps(data, ensure_ascii=False, sort_keys=True)
        self.atomic(self.path, content)
        if not self.backup.exists(): self.atomic(self.backup, content)
        if data['initialized']: self.atomic(self.directory / 'initialized', '1\n')
        self.recovered = False

def health_message(state, now):
    return dict(id='health', state=state, kind='health', headline='', links=[], correction=None,
                updated=now, event_url='https://savemetibo.com/', direct=False, semantic=digest([state, now]))

def queue(s, key, item, now, due=None):
    s['pending'][key] = dict(item=item, attempts=0, due=now if due is None else due, discovered=now)

def update_linked_hints(s, key, item, old, now, first, prefer_event):
    """Observe supplement semantics independently; never replace canonical event fields."""
    hints = item.pop('linked_hints', [])
    seen = dict((old or {}).get('hint_seen', {}))
    watermark = (old or {}).get('hint_watermark', (old or item)['updated'])
    pending_key = key + ':team_hint'
    changed = old is not None and old['semantic'] != item['semantic']
    if changed:
        # A newer canonical decision supersedes any queued lower-value supplement.
        s['pending'].pop(pending_key, None)
    candidates = []
    headline_words = re.findall(r'\w+', item['headline'].casefold())
    for hint in sorted(hints, key=lambda h: (h['updated'], h['id'])):
        semantic = digest(hint['headline'].casefold())
        if semantic in seen:
            continue  # Timestamp/value-only refresh is not a new semantic observation.
        seen[semantic] = hint['updated']
        if hint['updated'] > max(watermark, item['updated']):
            watermark = hint['updated']
            if re.findall(r'\w+', hint['headline'].casefold()) != headline_words:
                candidates.append(hint)
    item['hint_seen'], item['hint_watermark'] = seen, watermark
    if first or prefer_event or item['state'] in CORRECTIONS | {'closed', 'cooled'}:
        s['pending'].pop(pending_key, None)
        return
    if not candidates:
        return
    hint = candidates[-1]
    if now - hint['updated'] > 21600:
        return
    supplement = dict(hint, id=pending_key, kind='team_hint_update', state=item['state'],
                      semantic=digest([key, 'team_hint_update', hint['headline'].casefold()]))
    sent = s['accepted'].get(pending_key)
    due = max(now, sent['at'] + 1800) if sent else now
    queue(s, pending_key, supplement, now, due)

def cycle(s, data, now, error=None):
    s['last_run'] = now
    try:
        if error: raise error
        items, source = parse(data, now, s['source'])
    except Fault as e:
        h = s['health']; h.setdefault('since', now); h['reason'] = e.reason
        s['source_next_attempt'] = now + e.retry
        if (now - h['since'] >= 3600 or e.reason == 'source_outage') and not h.get('notified'):
            if 'health' not in s['pending']: queue(s, 'health', health_message('outage', now), now)
        return
    s['last_source_success'] = now
    s['source_next_attempt'] = now
    was_outage = bool(s['health'].get('since'))
    notified = s['health'].get('notified', False)
    s['source'] = source
    s['health'] = {'reason': 'bad_entries' if source['bad_entries'] else None}
    if s['pending'].get('health', {}).get('item', {}).get('state') == 'outage':
        s['pending'].pop('health', None)
    skipped = 0
    if source['bad_entries']:
        if now - s.get('last_bad_notice', 0) >= 86400:
            queue(s, 'bad_entries', health_message('bad_entries', now), now)
    else:
        s['pending'].pop('bad_entries', None)
    first = not s['initialized']
    for item in items:
        # Resolve a stable identity from prior IDs/evidence, not array positions.
        aliases = set(item['aliases'])
        key = item['id']
        for old_key, old in s['observed'].items():
            if aliases & set(old.get('aliases', [old_key])) or (item['event_url'] and item['event_url'] == old['event_url']) or set(item['links']) & set(old['links']):
                key = old_key; break
        item['semantic'] = digest(['SaveMeTibo', key, item['state'], item['kind'], item['headline'].casefold(), item['links'], item['correction']])
        old = s['observed'].get(key)
        sent = s['accepted'].get(key)
        correction_sent = s['accepted'].get(item['correction'])
        special = bool(item['correction']) or item['state'] in CORRECTIONS
        eligible = item['state'] in ('confirmed', 'landed') or (item['state'] == 'watch' and (item['direct'] or item['kind'] == 'team_hint'))
        if special or item['state'] in ('cooled', 'closed'):
            eligible = bool(sent or correction_sent)
        prefer_event = eligible and (old is None or old['semantic'] != item['semantic'] or key in s['pending'])
        update_linked_hints(s, key, item, old, now, first, prefer_event)
        # Always cancel superseded pending versions before selecting a new one.
        pending = s['pending'].get(key)
        if pending and pending['item']['semantic'] != item['semantic']:
            s['pending'].pop(key)
        if item['correction']:
            s['pending'].pop(item['correction'], None)
        s['observed'][key] = item
        if first or not eligible or (sent and sent['semantic'] == item['semantic']):
            s['pending'].pop(key, None); continue
        if old and old['semantic'] == item['semantic']:
            continue
        if now - item['updated'] > 21600 and not special:
            skipped += 1; s['pending'].pop(key, None); continue
        due = now
        if sent and sent['state'] == item['state'] and not special:
            due = max(now, sent['at'] + 1800)
        queue(s, key, item, now, due)
    if notified:
        notice = health_message('recovered', now)
        notice['headline'] = '超过六小时的变化未逐条补发：' + str(skipped)
        queue(s, 'health', notice, now)
    s['skipped_old'] = s.get('skipped_old', 0) + skipped
    s['initialized'] = True
    s['recovering'] = was_outage

def payload(item, key):
    state = item['state']
    if item['kind'] == 'health':
        title = 'Tibo 监控 · ' + {'outage': '数据源异常', 'recovered': '数据源恢复',
            'bad_entries': '数据条目异常', 'state_corrupt': '本地状态损坏', 'test': '安装测试'}[state]
        body = '监控状态提示，不代表个人额度变化。' + item['headline']
    else:
        title = 'Codex · ' + ('撤回／更正' if item['correction'] else TITLES[state])
        if item['kind'] == 'team_hint_update':
            title = 'Codex · Tibo 动向补充（社区源转述）'
        attribution = '社区源转述' if not item['direct'] else 'SaveMeTibo 社区源报告（附 Tibo 证据链接）'
        # Do not reproduce quota-consumption instructions from upstream text.
        summary = re.sub(r'[^.!?。！？]*(?:use (?:up|remaining|all)|burn|exhaust|start heavy|用光)[^.!?。！？]*[.!?。！？]?', '', item['headline'][:1200], flags=re.I)[:600]
        body = attribution + '；' + ('尚未确认。' if state == 'watch' else '')
        if state in ('cooled', 'closed'): body += '观察已结束，不证明没有重置。'
        if item['kind'] == 'team_hint_update':
            body += '新的补充动向尚未独立确认；关联事件状态保持：' + state + '。'
        body += '\n上游摘要：' + summary
        body += '\n消息更新时间：' + dt.datetime.fromtimestamp(item['updated'], ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M %Z (Asia/Shanghai)')
        body += '\n个人是否生效，请查看自己的 Codex 客户端。\n' + '\n'.join(item['links'][:3])
    p = dict(device_key=key, title=title, body=body, group='Tibo-Codex', level='active',
             url=url(item['event_url']) or 'https://savemetibo.com/')
    while len(json.dumps(p, ensure_ascii=False).encode()) > 3000:
        p['body'] = p['body'][:-32]
    return json.dumps(p, ensure_ascii=False).encode()

def push(item, key):
    response = request(ENDPOINT, payload(item, key))
    if not isinstance(response, dict) or type(response.get('code')) is not int or response['code'] != 200:
        raise Fault('bark_not_accepted', 3600)

def deliver(s, now, key, save, sender=push):
    if not key:
        s['push_status'] = 'WAITING_FOR_BARK_KEY'; save(s); return
    count = 0
    for identity, job in sorted(list(s['pending'].items()), key=lambda p: (p[1]['item']['kind'] != 'health', not bool(p[1]['item']['correction']), p[1]['due'])):
        item = job['item']
        if item['kind'] != 'health':
            if s['health'].get('reason') not in (None, 'bad_entries'): continue
            if now - item['updated'] > 21600 and not (item['correction'] or item['state'] in CORRECTIONS):
                s['pending'].pop(identity); continue
        if job['due'] > now or count >= 5: continue
        count += 1
        # Persist uncertainty before the network side effect.
        job['attempts'] += 1
        job['due'] = now + [300, 600, 1200, 3600][min(job['attempts'] - 1, 3)]
        save(s)
        try:
            sender(item, key)
        except Fault as e:
            job['due'] = max(job['due'], now + e.retry)
            s['push_status'] = e.reason
            if e.retry >= 86400:
                for other in s['pending'].values(): other['due'] = max(other['due'], now + e.retry)
                save(s); break
        else:
            s['accepted'][identity] = dict(semantic=item['semantic'], state=item['state'], at=now,
                                           accepted_by_push_service=True)
            s['last_push_accepted'] = now
            s['push_status'] = 'accepted_by_push_service'
            if item['state'] == 'outage': s['health']['notified'] = True
            if identity == 'bad_entries': s['last_bad_notice'] = now
            del s['pending'][identity]
        save(s)
    save(s)

def configure():
    if os.geteuid() != 0 or not sys.stdin.isatty(): raise Fault('root_secure_terminal_required')
    private = getpass.getpass('Bark App 推送地址（不回显）：')
    p = urllib.parse.urlsplit(private)
    if p.scheme != 'https' or p.netloc != 'api.day.app' or p.query or p.fragment:
        raise Fault('only_api_day_app_allowed')
    key = p.path.strip('/')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,256}', key): raise Fault('invalid_bark_address')
    directory = Path('/etc/tibo-watch')
    if directory.is_symlink(): raise Fault('unsafe_config_path')
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    fd, name = tempfile.mkstemp(dir=directory)
    with os.fdopen(fd, 'w') as f:
        f.write('BARK_KEY=' + key + '\n'); f.flush(); os.fsync(f.fileno())
    os.replace(name, directory / 'bark.env')
    print('Bark 凭据已安全保存；未发送通知。')

def status(s):
    fields = ('initialized', 'last_run', 'last_source_success', 'last_push_accepted', 'push_status', 'source', 'health', 'test_push')
    result = {k: s.get(k) for k in fields}
    result['pending_count'] = len(s['pending'])
    result['source_age_seconds'] = time.time() - s['source']['checked'] if s['source'].get('checked') else None
    result['device_receipt'] = 'DEVICE_RECEIPT_UNCONFIRMED'
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['check-source', 'run-once', 'dry-run', 'test-push', 'status', 'configure-bark'])
    p.add_argument('--state-dir', default='/var/lib/tibo-watch')
    args = p.parse_args()
    if args.command == 'configure-bark': configure(); return
    if args.command == 'check-source':
        items, source = parse(request(SOURCE), time.time(), {})
        print(json.dumps(dict(source=source, valid_events=len(items)))); return
    if args.command == 'dry-run':
        # Read-only snapshot: no locks/files created in production.
        s = copy.deepcopy(State(args.state_dir).load())
        cycle(s, request(SOURCE), time.time())
        print(json.dumps(status(s))); return
    with State(args.state_dir) as storage:
        try:
            s = storage.load()
        except Fault as e:
            if e.reason == 'state_corrupt_manual_recovery_required' and args.command == 'run-once':
                marker = storage.directory / 'state-fault-notice'
                now = time.time()
                if os.environ.get('BARK_KEY') and (not marker.exists() or now - marker.stat().st_mtime >= 86400):
                    storage.atomic(marker, 'attempted; manual state recovery required\n')
                    push(health_message('state_corrupt', now), os.environ['BARK_KEY'])
            raise
        if args.command == 'status': print(json.dumps(status(s))); return
        now, key = time.time(), os.environ.get('BARK_KEY', '')
        if args.command == 'test-push':
            if not key: raise Fault('WAITING_FOR_BARK_KEY')
            if s.get('test_push'): print(json.dumps({'test_push': s['test_push']})); return
            s['test_push'] = 'attempted_result_uncertain'; storage.save(s)
            push(health_message('test', now), key)
            s['test_push'] = 'accepted_by_push_service'; storage.save(s)
            print(json.dumps({'test_push': s['test_push'], 'device_receipt': 'DEVICE_RECEIPT_UNCONFIRMED'})); return
        if now >= s.get('source_next_attempt', 0):
            try: data, error = request(SOURCE), None
            except Fault as e: data, error = None, e
            cycle(s, data, now, error)
        else:
            s['last_run'] = now
        storage.save(s)
        deliver(s, now, key, storage.save)
        print(json.dumps(status(s)))

if __name__ == '__main__':
    try:
        main()
    except Fault as e:
        print(json.dumps({'error': e.reason})); sys.exit(1)
    except Exception:
        # Never render exception objects: urllib may carry private request data.
        print('{"error":"internal_error"}'); sys.exit(1)
