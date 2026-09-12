import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import watcher as w

# All credential-like values and URLs in these tests are synthetic.
NOW = 1800000000

def iso(t):
    return w.dt.datetime.fromtimestamp(t, w.dt.timezone.utc).isoformat()

def event(identity='a', state='watch', now=NOW, **kw):
    e = dict(event_id=identity, provider='codex', state=state, kind='reset',
        headline='A reset signal', receipt_urls=['https://x.com/thsottiaux/status/' + str(ord(identity[0]))],
        event_url='https://savemetibo.com/events/' + identity, updated_at=iso(now),
        first_published_at=iso(now), correction_of=None)
    e.update(kw); return e

def data(events=None, now=NOW):
    return dict(schema_version='1.2', generated_at=iso(now),
        freshness=dict(last_checked_at=iso(now), stale=False, outage=False),
        providers={'codex': {'stale': False}}, events=[event()] if events is None else events, change_log=[])

class Acceptance(unittest.TestCase):
    def setUp(self):
        self.s = w.blank(); self.sent = []
    def cycle(self, d, now=NOW): w.cycle(self.s, d, now)
    def send(self, now=NOW, fail=False):
        def sender(item, key):
            if fail: raise w.Fault('network_error')
            self.sent.append(item)
        w.deliver(self.s, now, 'synthetic-key', lambda s: None, sender)
    def baseline(self): self.cycle(data()); self.send()
    def new(self, state='watch', now=NOW):
        self.cycle(data([event(), event('b', state, now)], now), now)

    def test_T01_baseline(self):
        self.baseline(); self.assertTrue(self.s['initialized']); self.assertEqual(self.sent, [])
    def test_T02_new(self):
        self.baseline(); self.new(); self.send(); self.assertEqual(len(self.sent), 1)
        self.assertIn('尚未确认', json.loads(w.payload(self.sent[0], 'k'))['body'])
    def test_T03_reorder_probability_restart(self):
        self.baseline(); self.new(); self.send()
        d=data([event('b', chance_48h=99), event()], NOW+10)
        self.s=json.loads(json.dumps(self.s));self.cycle(d,NOW+10);self.send(NOW+10)
        self.assertEqual(len(self.sent),1)
    def test_T04_progress(self):
        self.baseline();self.new();self.send();self.new('confirmed',NOW+1);self.send(NOW+1)
        self.new('landed',NOW+2);self.send(NOW+2)
        self.assertEqual([e['state'] for e in self.sent],['watch','confirmed','landed'])
    def test_T05_merge(self):
        self.baseline(); d=data([event(),event('b'),event('b','landed',NOW+1)],NOW+1)
        d['change_log']=[dict(category='team_hint',text='reset propagated',event_url='https://savemetibo.com/events/b',at=iso(NOW+1))]
        self.cycle(d,NOW+1);self.send(NOW+1)
        self.assertEqual([e['state'] for e in self.sent],['landed'])
    def test_T06_hint_and_impostor(self):
        self.baseline(); d=data([event(), event('b',receipt_urls=['https://evil.test/thsottiaux/status/2'],headline='Tibo reset')])
        d['change_log']=[dict(category='team_hint', text='A banked reset is planned',at=iso(NOW)),dict(category='team_hint',text='Hello there',at=iso(NOW))]
        self.cycle(d);self.send();self.assertEqual(len(self.sent),1)
        self.assertIn('社区源转述',json.loads(w.payload(self.sent[0],'k'))['body'])
    def test_T07_correction_cooled(self):
        self.baseline();self.new();self.send();self.new('cooled',NOW+1);self.send(NOW+1)
        self.new('retracted',NOW+2);self.send(NOW+2);self.send(NOW+3)
        self.assertEqual([e['state'] for e in self.sent],['watch','cooled','retracted'])
    def test_T08_stale_outage_recovery(self):
        self.baseline();self.cycle(data(),NOW+1900);self.send(NOW+1900);self.assertEqual(self.sent,[])
        self.cycle(data(),NOW+3700);self.send(NOW+3700)
        self.cycle(data(),NOW+4000);self.send(NOW+4000)
        self.cycle(data(now=NOW+4100),NOW+4100);self.send(NOW+4100)
        self.assertEqual([e['state'] for e in self.sent],['outage','recovered'])
    def test_T08_http_failure_and_304(self):
        self.baseline()
        for t in (NOW,NOW+3601,NOW+4000):
            w.cycle(self.s,None,t,w.Fault('http_304'));self.send(t)
        self.assertEqual([e['state'] for e in self.sent],['outage'])
    def test_T09_bad_structures_preserve(self):
        self.baseline()
        for d in [None,{},data([]),dict(data(),schema_version='2.0'),dict(data(),generated_at='bad'),dict(data(),generated_at=iso(NOW+600))]:
            self.cycle(d); self.assertEqual(len(self.s['observed']),1);self.assertTrue(self.s['initialized'])
        d=data([event(),{}]);self.cycle(d);self.assertEqual(self.s['source']['bad_entries'],1)
    def test_T10_retry(self):
        self.baseline();self.new();self.send(fail=True)
        self.assertEqual(len(self.s['pending']),1);self.assertFalse(self.s['accepted'])
        self.send(NOW+299);self.assertEqual(self.sent,[])
        self.send(NOW+300);self.assertEqual(len(self.sent),1);self.assertTrue(self.s['accepted']['b']['accepted_by_push_service'])
    def test_T11_supersede(self):
        self.baseline();self.new();self.send(fail=True);self.new('landed',NOW+1);self.send(NOW+1)
        self.send(NOW+500);self.assertEqual([e['state'] for e in self.sent],['landed'])
    def test_T12_lock_backup(self):
        with tempfile.TemporaryDirectory() as td:
            with w.State(td) as st:
                self.baseline();st.save(self.s);st.save(self.s)
                with self.assertRaises(w.Fault):
                    with w.State(td): pass
                st.path.write_text('{'); restored=st.load();self.assertTrue(restored['initialized']);st.save(restored)
                st.path.write_text('{');st.backup.write_text('{')
                with self.assertRaises(w.Fault):st.load()
    def test_T13_old_and_correction(self):
        self.baseline();self.new();self.send()
        self.cycle(data([event(),event('b','retracted',NOW),event('c','confirmed',NOW)],NOW+25000),NOW+25000)
        self.send(NOW+25000)
        self.assertEqual([e['state'] for e in self.sent],['watch','retracted'])
    def test_T14_payload(self):
        self.baseline();self.new();item=copy.deepcopy(self.s['pending']['b']['item'])
        item['headline']='汉字🌕'*10000;item['event_url']='https://api.day.app/secret'
        p=w.payload(item,'synthetic-secret');self.assertLessEqual(len(p),3000)
        self.assertEqual(json.loads(p)['url'],'https://savemetibo.com/')
        for u in ['http://x.com/thsottiaux/status/1','https://x.com.evil/thsottiaux/status/1','https://x.com@evil/thsottiaux/status/1','javascript:foo']:
            self.assertEqual(w.url(u),'')
    def test_cooldown_latest(self):
        self.baseline();self.new();self.send()
        for t in (10,20):
            self.cycle(data([event(),event('b','watch',NOW+t,headline='changed '+str(t))],NOW+t),NOW+t)
            self.send(NOW+t)
        self.assertEqual(len(self.sent),1);self.send(NOW+1800)
        self.assertEqual(self.sent[-1]['headline'],'changed 20')
    def test_business_contract_and_redaction(self):
        for response in ({'code':500},'<html>',{'code':'200'},{}):
            with patch.object(w,'request',return_value=response):
                with self.assertRaises(w.Fault):w.push(w.health_message('test',NOW),'secret')
        with patch.object(w,'request',return_value={'code':200}):w.push(w.health_message('test',NOW),'secret')
    def test_retry_after(self):
        self.assertEqual(w.retry_after('7200',NOW),7200)
        self.assertEqual(w.retry_after('bad',NOW),0)
    def test_baseline_missing_key(self):
        self.baseline();self.new();w.deliver(self.s,NOW,'',lambda s:None)
        self.assertEqual(self.s['push_status'],'WAITING_FOR_BARK_KEY');self.assertEqual(len(self.s['pending']),1)


    def test_http_bound_and_json(self):
        from io import BytesIO
        class Response(BytesIO):
            status=200
        for raw, reason in [(b'<html>', 'invalid_json'), (b'x'*(w.LIMIT+1),'response_too_large')]:
            with patch.object(w.urllib.request.OpenerDirector,'open',return_value=Response(raw)):
                with self.assertRaises(w.Fault) as error:w.request(w.SOURCE)
                self.assertEqual(error.exception.reason,reason)
    def test_http_secret_exception_redacted(self):
        error=w.urllib.error.URLError('https://api.day.app/DO-NOT-LOG-KEY')
        with patch.object(w.urllib.request.OpenerDirector,'open',side_effect=error):
            with self.assertRaises(w.Fault) as caught:w.request(w.ENDPOINT,b'{}')
            self.assertNotIn('DO-NOT-LOG',str(caught.exception))
    def test_redirect_blocked(self):
        self.assertIsNone(w.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test'))
    def test_recovery_pending_survives_healthy_poll(self):
        self.baseline();self.cycle(data(),NOW+3700);self.send(NOW+3700)
        self.cycle(data(now=NOW+3800),NOW+3800);self.send(NOW+3800,fail=True)
        self.cycle(data(now=NOW+4100),NOW+4100);self.send(NOW+4100)
        self.assertEqual([e['state'] for e in self.sent],['outage','recovered'])
    def test_evidence_alias_across_polls(self):
        self.baseline();self.new();self.send()
        b=event('z',receipt_urls=event('b')['receipt_urls'],event_url=event('b')['event_url'])
        self.cycle(data([event(),b]));self.send();self.assertEqual(len(self.sent),1)
    def test_source_regression(self):
        self.baseline();self.cycle(data(now=NOW-1));self.assertEqual(self.s['health']['reason'],'response_regressed')
    def test_batch_max_five(self):
        self.baseline();self.cycle(data([event(chr(n)) for n in range(97,108)]));self.send()
        self.assertEqual(len(self.sent),5);self.assertEqual(len(self.s['pending']),5)
    def test_test_push_at_most_one(self):
        with tempfile.TemporaryDirectory() as td:
            args=['watcher','test-push','--state-dir',td]
            with patch.object(sys,'argv',args),patch.dict(w.os.environ,{'BARK_KEY':'synthetic-key'}),patch.object(w,'push') as push:
                w.main();w.main();self.assertEqual(push.call_count,1)
    def test_dry_run_no_state_files(self):
        with tempfile.TemporaryDirectory() as td:
            args=['watcher','dry-run','--state-dir',td]
            with patch.object(sys,'argv',args),patch.object(w,'request',return_value=data([event(now=w.time.time())],now=w.time.time())):
                w.main()
            self.assertEqual(list(Path(td).iterdir()),[])

    def linked(self, events, text, at, now=None):
        d = data(events, at if now is None else now)
        d['change_log'] = [dict(category='team_hint', text=text,
            event_url=events[0]['event_url'], at=iso(at), value=10)]
        return d

    def test_linked_regression_linked_new_hint_unchanged_event(self):
        e = event(state='landed')
        self.cycle(data([e])); self.send()
        d = self.linked([e], 'A new banked reset allowance is planned', NOW+60)
        self.cycle(d, NOW+60); self.send(NOW+60)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]['kind'], 'team_hint_update')
        self.assertEqual(self.s['observed']['a']['state'], 'landed')
        self.assertEqual(self.s['observed']['a']['headline'], e['headline'])
        self.assertEqual(self.s['observed']['a']['updated'], NOW)
        self.assertIn('动向补充', json.loads(w.payload(self.sent[0], 'k'))['title'])
        self.cycle(d, NOW+120); self.send(NOW+120)
        self.assertEqual(len(self.sent), 1)

    def test_linked_regression_linked_hint_same_round_upgrade(self):
        self.baseline()
        e = event(state='landed', now=NOW+60)
        d = self.linked([e], 'Reset all propagated', NOW+90)
        self.cycle(d, NOW+90); self.send(NOW+90)
        self.assertEqual([(e['state'],e['kind']) for e in self.sent], [('landed','reset')])
        self.cycle(d, NOW+100); self.send(NOW+100)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.s['observed']['a']['state'], 'landed')

    def test_linked_regression_refresh_reorder_restart_and_older_text(self):
        e = event(state='confirmed')
        self.cycle(self.linked([e], 'A banked reset is planned', NOW+10), NOW+10)
        d = self.linked([e], 'Another quota allowance is planned', NOW+20)
        self.cycle(d, NOW+20); self.send(NOW+20)
        self.s = json.loads(json.dumps(self.s))
        refreshed = self.linked([e], '  Another QUOTA allowance is planned  ', NOW+100)
        refreshed['change_log'][0]['value'] = 99
        refreshed['change_log'].append(dict(category='team_hint',text='Older usage limits hint',
            event_url=e['event_url'],at=iso(NOW+15)))
        for ordering in (refreshed['change_log'], list(reversed(refreshed['change_log']))):
            refreshed['change_log'] = ordering
            self.cycle(refreshed, NOW+100); self.send(NOW+100)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.s['observed']['a']['hint_watermark'], NOW+20)

    def test_linked_regression_baseline_hint_and_same_headline_silent(self):
        e = event(state='landed')
        self.cycle(self.linked([e], 'A new quota announcement', NOW+10), NOW+10);self.send(NOW+10)
        self.assertEqual(self.sent, [])
        d = self.linked([e], e['headline'] + '!', NOW+20)
        self.cycle(d, NOW+20);self.send(NOW+20)
        self.assertEqual(self.sent, [])

    def test_linked_regression_pending_hint_superseded_by_canonical(self):
        self.baseline()
        self.cycle(self.linked([event()], 'Extra quota reset planned', NOW+10), NOW+10)
        self.send(NOW+10, fail=True)
        self.assertIn('a:team_hint',self.s['pending'])
        self.cycle(self.linked([event(state='landed',now=NOW+20)], 'Extra quota reset planned',NOW+10,now=NOW+20),NOW+20)
        self.send(NOW+20);self.send(NOW+400)
        self.assertEqual([(e['state'],e['kind']) for e in self.sent],[('landed','reset')])

    def test_linked_regression_failed_hint_retry_and_latest_cooldown(self):
        e = event(state='landed');self.cycle(data([e]))
        d = self.linked([e], 'An extra quota reset is planned',NOW+10)
        self.cycle(d,NOW+10);self.send(NOW+10,fail=True)
        self.cycle(d,NOW+100);self.send(NOW+100);self.assertEqual(self.sent,[])
        self.send(NOW+310);self.assertEqual(len(self.sent),1)
        for at in (400,500):
            self.cycle(self.linked([e],'New reset allowance '+str(at),NOW+at),NOW+at);self.send(NOW+at)
        self.assertEqual(len(self.sent),1)
        self.send(NOW+2110);self.assertEqual(self.sent[-1]['headline'],'New reset allowance 500')
        self.assertEqual(len(self.sent),2)
