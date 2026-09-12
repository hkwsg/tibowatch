"""Offline publication-snapshot matching and final Bark JSON regression coverage."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import watcher as w
from test_watcher import NOW, item, feed


def snapshot(guid='apr_new', chance=86, state='watch', body='Original 👩🏽‍💻 🎉', event='evt_one'):
    return {'event_id': event, 'state': 'confirmed', 'chance_48h': None, 'lifecycle': [{
        'approval_id': guid, 'state': state, 'chance_48h': chance, 'headline': body,
        'share_card_url': f'https://savemetibo.com/events/{event}/artifacts/{guid}.png'}]}


class Display(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.storage = w.State(self.temp.name)
        self.base = item('base')
        self.new = item('apr_new', title='Codex — Watch 🎉', body='Original 👩🏽‍💻 🎉')
        self.events = [snapshot()]
        self.supplement_calls = 0; self.sent = []; self.fail = False
        self.translator = Mock(return_value={'title': 'Codex — 重置观察 🎉', 'body': '原文 👩🏽‍💻 🎉'})
        self.network = patch.object(w, 'request', side_effect=self.request); self.network.start(); self.addCleanup(self.network.stop)
        self.env = patch.dict(w.os.environ, {'TIBOWATCH_TRANSLATE': '1'}); self.env.start(); self.addCleanup(self.env.stop)
        self.items = [self.base]
        self.poll()

    def request(self, target, payload=None, timeout=10):
        if target == w.SOURCE: return feed(*self.items)
        if target == w.SUPPLEMENT:
            self.assertEqual(timeout, 5); self.supplement_calls += 1
            if isinstance(self.events, Exception): raise self.events
            return json.dumps({'events': self.events}).encode()
        self.assertEqual(target, w.ENDPOINT)
        self.sent.append(json.loads(payload))
        if self.fail: raise w.Fault('network_error')
        return b'{"code":200}'

    def poll(self, now=NOW):
        with patch.object(w.time, 'time', return_value=now):
            return w.run_once(self.storage, 'synthetic-key', self.translator)

    def notify(self):
        self.items.append(self.new)
        return self.poll()

    def test_captured_publication_snapshots(self):
        raw=(Path(__file__).parent/'fixtures/publication_snapshots.json').read_bytes()
        with patch.object(w,'request',return_value=raw): snapshots=w.publication_snapshots()
        expected={'apr_031a4b0dc2f784f6e58091a44946e797':'86',
                  'apr_5f32e1706f0fcdfd291ce2a317241ff0':'97',
                  'apr_8520167c6f4f10a96d674ef8013b7e97':'100'}
        for guid, percent in expected.items():
            self.assertEqual(w.display_fields(guid,{'body':snapshots[guid][1]['headline']},snapshots)[0],percent)
        event=next(e for e in json.loads(raw)['events'] if any(l['approval_id']=='apr_5f32e1706f0fcdfd291ce2a317241ff0' for l in e['lifecycle']))
        self.assertEqual(event['state'],'confirmed');self.assertIsNone(event['chance_48h'])

    def test_exact_snapshot_not_parent_or_homepage(self):
        for chance in (86, 97):
            self.new['body'] += '!'; self.events = [snapshot(chance=chance, body=self.new['body'])]
            if len(self.items) == 1: self.items.append(self.new)
            self.poll()
            out = self.sent[-1]
            self.assertTrue(out['title'].endswith(f'：{chance}%'))
            self.assertEqual(out['body'], '原文 👩🏽‍💻 🎉')
            self.assertNotIn('url', out); self.assertNotIn('action', out)
            self.assertEqual(out['isArchive'], '1')
        self.assertEqual(self.translator.call_args.args, (self.new['title'], self.new['body']))

    def test_probabilities_and_landed(self):
        for chance, state, suffix in [(None,'landed','100'),(0,'landed','100'),(None,'confirmed',None),
                (None,'watch',None),(0,'watch','0'),(86.0,'watch','86'),(0.86,'watch','0.86'),
                (97.25,'watch','97.25'),(101,'watch',None),(-1,'watch',None),(True,'watch',None),
                ('86','watch',None),(float('nan'),'watch',None),(float('inf'),'watch',None),(10**400,'watch',None)]:
            with self.subTest(chance=chance,state=state):
                e=snapshot(chance=chance,state=state)
                fields=w.display_fields('apr_new',{'body':self.new['body']},{'apr_new':(e['event_id'],e['lifecycle'][0])})
                self.assertEqual(fields[0],suffix)
        self.assertEqual(w.display_title('Already 86%', '86'), 'Already 86%')
        self.assertEqual(w.display_title('Already 186%', '86'), 'Already 186%：86%')

    def test_invalid_or_conflicting_snapshot_still_forwards(self):
        cases = [[snapshot(body='different')], [snapshot(guid='apr_other')],
                 [snapshot(),snapshot(chance=97)], [snapshot(),snapshot(chance=97),snapshot()],
                 [{'event_id':'evt_one','lifecycle':None}], [None]]
        for events in cases:
            self.new['title']+='!'; self.events=events
            if len(self.items)==1:self.items.append(self.new)
            self.poll()
            self.assertEqual(self.sent[-1]['title'],'Codex — 重置观察 🎉')
            self.assertNotIn('icon',self.sent[-1])
        self.assertEqual(len(self.sent),len(cases))

    def test_whitespace_match_and_duplicate_identical(self):
        self.events=[snapshot(body=' '+self.new['body']+'\n')]*2
        self.notify();self.assertTrue(self.sent[-1]['title'].endswith('：86%'))

    def test_supplement_failure_does_not_change_rss_health(self):
        self.events=w.Fault('network_error')
        s=self.notify()
        self.assertIsNone(s['health']['reason']);self.assertEqual(len(self.sent),1)
        self.assertEqual(self.supplement_calls,1)

    def test_bad_json_duplicate_keys_and_top_shape(self):
        for raw in [b'broken',b'[]',b'{"events":{}}',b'{"events":[],"events":[]}']:
            with patch.object(w,'request',return_value=raw):self.assertEqual(w.publication_snapshots(),{})

    def test_quiet_baseline_and_display_only_edits(self):
        self.assertEqual(self.supplement_calls,0)
        self.poll();self.assertEqual(self.supplement_calls,0)
        self.notify();self.events=[snapshot(chance=99)]
        self.new['at']+=1;self.new['link']='https://example.org/changed'
        self.poll(NOW+1)
        self.assertEqual(self.supplement_calls,1);self.assertEqual(len(self.sent),1)
        self.assertEqual(self.translator.call_count,1)

    def test_batch_shares_one_fetch(self):
        self.items += [item('apr_'+str(i),body=self.new['body']) for i in range(7)]
        self.events=[snapshot('apr_'+str(i)) for i in range(7)]
        self.poll();self.assertEqual(self.supplement_calls,1);self.assertEqual(len(self.sent),5)
        self.poll(NOW+1);self.assertEqual(self.supplement_calls,2);self.assertEqual(len(self.sent),7)

    def test_retry_after_restart_keeps_probability_and_icon(self):
        self.fail=True;self.notify();original=copy.deepcopy(self.sent[-1])
        self.events=[snapshot(chance=12)];self.fail=False
        self.storage=w.State(self.temp.name);self.poll(NOW+300)
        self.assertEqual(self.sent[-1],original);self.assertEqual(self.supplement_calls,1)
        self.assertEqual(self.translator.call_count,1)

    def test_english_failure_and_disabled(self):
        self.translator.side_effect=RuntimeError('not logged in')
        self.notify();self.assertEqual(self.sent[-1]['title'],self.new['title']+'：86%')
        self.assertEqual(self.sent[-1]['body'],self.new['body'])
        self.new['title']+='!'
        with patch.dict(w.os.environ,{'TIBOWATCH_TRANSLATE':'0'}):self.poll()
        self.assertEqual(self.translator.call_count,1)
        self.assertEqual(self.sent[-1]['title'],self.new['title']+'：86%')

    def test_interruption_persists_decorated_english(self):
        self.translator.side_effect=SystemExit()
        with self.assertRaises(SystemExit):self.notify()
        s=self.storage.load();self.assertEqual(s['pending']['apr_new']['payload']['title'],self.new['title']+'：86%')
        self.translator.side_effect=None;self.poll(NOW+1)
        self.assertEqual(self.translator.call_count,1);self.assertEqual(self.supplement_calls,1)
        self.assertEqual(self.sent[-1]['title'],self.new['title']+'：86%')

    def test_legacy_selected_pending_output_and_state_compatibility(self):
        self.fail=True;self.notify();s=self.storage.load()
        job=s['pending']['apr_new'];job['payload']={'title':'Legacy 🎉','body':'Original 👩🏽‍💻','url':'https://example.org'}
        s['test_push']='accepted_by_push_service';self.storage.save(s)
        self.fail=False;out=self.poll(NOW+300)
        self.assertEqual(self.sent[-1]['title'],'Legacy 🎉');self.assertNotIn('url',self.sent[-1])
        self.assertNotIn('icon',self.sent[-1]);self.assertEqual(self.sent[-1]['isArchive'],'1')
        self.assertEqual(out['test_push'],s['test_push']);self.assertEqual(out['observed'],s['observed'])
        self.assertEqual(self.supplement_calls,1);self.assertEqual(self.translator.call_count,1)
        self.assertEqual(out['version'],2)

    def test_icons_exact_path_and_allowlist(self):
        good=snapshot()['lifecycle'][0]['share_card_url']
        for url in [None,'http://savemetibo.com/x.png',good+'?x=1',good+'#x',good.replace('savemetibo.com','savemetibo.com.evil'),
                    good.replace('https://','https://user@'),good.replace('evt_one','evt_other'),good.replace('apr_new','apr_other'),
                    good.replace('savemetibo.com','savemetibo.com:443'),good+'\n']:
            e=snapshot();e['lifecycle'][0]['share_card_url']=url
            self.assertIsNone(w.display_fields('apr_new',{'body':self.new['body']},{'apr_new':(e['event_id'],e['lifecycle'][0])})[1])
        self.notify();self.assertEqual(self.sent[-1]['icon'],good)
        out=json.loads(w.encode_payload({'title':'t','body':'b','url':'bad','action':'none','icon':'https://evil.test/x'},'synthetic-key'))
        self.assertEqual(set(out),{'title','body','device_key','group','level','isArchive'})

    def test_icon_budget_favors_text_before_selection(self):
        self.translator.side_effect=ValueError()
        p={'title':self.new['title']+'：86%','body':'','url':'unused'}
        overhead=len(w.encode_payload(p,'synthetic-key'))
        self.new['body']='x'*(w.PAYLOAD_LIMIT-overhead)
        self.events=[snapshot(body=self.new['body'])];self.notify()
        self.assertNotIn('icon',self.sent[-1]);self.assertEqual(self.sent[-1]['body'],self.new['body'])
        self.assertEqual(len(json.dumps(self.sent[-1],ensure_ascii=False).encode()),w.PAYLOAD_LIMIT)

    def test_translation_expansion_drops_icon_before_final_save(self):
        p={'title':'译文：86%','body':'','url':'unused'}
        body='x'*(w.PAYLOAD_LIMIT-len(w.encode_payload(p,'synthetic-key')))
        self.translator.return_value={'title':'译文','body':body};self.fail=True
        self.notify();self.assertNotIn('icon',self.storage.load()['pending']['apr_new']['payload'])
        self.assertEqual(self.sent[-1]['body'],body)

    def test_configured_icon_is_persisted_and_retry_does_not_change_it(self):
        custom='https://raw.githubusercontent.com/hkwsg/tibowatch/'+'a'*40+'/assets/notification-icon.png'
        with patch.dict(w.os.environ,{'TIBOWATCH_ICON_URL':custom}):
            self.fail=True;self.notify()
        self.assertEqual(self.sent[-1]['icon'],custom)
        self.fail=False;self.poll(NOW+300)
        self.assertEqual(self.sent[-1]['icon'],custom)
        self.assertEqual(self.supplement_calls,1);self.assertEqual(self.translator.call_count,1)

    def test_invalid_configured_icon_uses_upstream(self):
        with patch.dict(w.os.environ,{'TIBOWATCH_ICON_URL':'https://evil.test/icon.png'}):self.notify()
        self.assertEqual(self.sent[-1]['icon'],self.events[0]['lifecycle'][0]['share_card_url'])

    def test_emoji_parse_persistence_and_output(self):
        self.translator.side_effect=ValueError();self.fail=True;self.notify()
        chosen=self.storage.load()['pending']['apr_new']['payload']
        self.assertEqual(chosen['body'],'Original 👩🏽‍💻 🎉')
        self.assertEqual(self.sent[-1]['body'],chosen['body'])


if __name__ == '__main__': unittest.main()
