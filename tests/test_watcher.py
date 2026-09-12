"""Offline RSS/reliability tests. Every credential-like value is synthetic."""
import copy
import datetime as dt
import email.utils
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import watcher as w

NOW = 1800000000

def item(guid='a', title='Codex reset', body='Full original body.', at=NOW, link='https://savemetibo.com/events/a'):
    return dict(guid=guid, title=title, body=body, at=at, link=link)

def feed(*items):
    parts = ['<rss version="2.0"><channel><title>Alerts</title>']
    for x in items:
        fields = {'guid':x['guid'], 'title':x['title'], 'description':x['body'],
                  'pubDate':email.utils.format_datetime(dt.datetime.fromtimestamp(x['at'], dt.timezone.utc)), 'link':x['link']}
        parts.append('<item>'+''.join('<'+k+'>'+escape(v)+'</'+k+'>' for k,v in fields.items())+'</item>')
    return (''.join(parts)+'</channel></rss>').encode()

class Mirror(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.storage = w.State(self.temp.name)
        self.s = w.blank();self.sent=[]
        self.translator=Mock(return_value={'title':'Codex 额度重置','body':'完整原始正文。'})
        self.environment=patch.dict(w.os.environ, {'TIBOWATCH_TRANSLATE':'1'});self.environment.start();self.addCleanup(self.environment.stop)
    def poll(self, *items, now=NOW, fail=False, key='synthetic-key'):
        w.ingest(self.s,w.parse_rss(feed(*items),now),now)
        self.storage.save(self.s)
        w.select_payloads(self.s,self.storage.save,self.translator)
        def send(payload,key):
            if fail:raise w.Fault('network_error')
            self.sent.append(copy.deepcopy(payload))
        w.deliver(self.s,now,key,self.storage.save,send)
    def baseline(self):self.poll(item())
    def new(self, **kw):self.poll(item(),item('b'),**kw)
    def test_historical_baseline(self):
        self.baseline();self.assertEqual(self.sent,[]);self.translator.assert_not_called()
    def test_new_guid_exact_translation(self):
        self.baseline();self.new()
        self.translator.assert_called_once_with('Codex reset','Full original body.')
        self.assertEqual(self.sent,[{'title':'Codex 额度重置','body':'完整原始正文。','url':item()['link']}])
    def test_translation_failures_fall_back_once(self):
        for failure in [w.Fault('model_unavailable'),TimeoutError(),OSError(),ValueError(),RuntimeError('synthetic-secret')]:
            with self.subTest(type=type(failure)):
                self.s=w.blank();self.sent=[];self.translator.reset_mock()
                self.translator.side_effect=failure
                self.baseline();self.new()
                self.assertEqual(len(self.sent),1);self.assertEqual(self.translator.call_count,1)
                self.assertEqual(self.sent[0]['title'],item()['title']);self.assertEqual(self.sent[0]['body'],item()['body'])
    def test_invalid_translation_falls_back(self):
        for value in [None,{},[],{'title':1,'body':'x'},{'title':'','body':'x'},{'title':'x','body':''},{'title':'x','body':'y','extra':1}]:
            self.s=w.blank();self.sent=[];self.translator.reset_mock();self.translator.return_value=value
            self.baseline();self.new();self.assertEqual(self.sent[0]['body'],item()['body']);self.assertEqual(self.translator.call_count,1)
    def test_repeat_reorder_metadata_only(self):
        self.baseline();self.new()
        self.poll(item('b',at=NOW+1,link='https://example.org/new'),item(),now=NOW+1)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.translator.call_count,1)
    def test_same_guid_changed_content(self):
        self.baseline();self.poll(item(title='New title',body='New body'))
        self.translator.assert_called_once_with('New title','New body');self.assertEqual(len(self.sent),1)
    def test_two_new_chronological(self):
        self.baseline();self.poll(item('c',title='later',at=NOW+2),item(),item('b',title='earlier',at=NOW+1),now=NOW+2)
        self.assertEqual([c.args[0] for c in self.translator.call_args_list],['earlier','later']);self.assertEqual(len(self.sent),2)
    def test_translated_retry_exact_payload(self):
        self.baseline();self.new(fail=True)
        chosen=copy.deepcopy(self.s['pending']['b']['payload'])
        self.s=self.storage.load();self.new(now=NOW+300)
        self.assertEqual(self.sent,[chosen]);self.assertEqual(self.translator.call_count,1)
    def test_english_retry_exact_payload(self):
        self.translator.side_effect=ValueError();self.baseline();self.new(fail=True)
        chosen=copy.deepcopy(self.s['pending']['b']['payload']);self.s=self.storage.load()
        self.new(now=NOW+300);self.assertEqual(self.sent,[chosen]);self.assertEqual(self.translator.call_count,1)
    def test_restart_after_accepted(self):
        self.baseline();self.new();self.s=self.storage.load();self.new(now=NOW+10)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.translator.call_count,1)
    def test_invalid_xml_network_preserves_state(self):
        self.baseline();original=copy.deepcopy(self.s['observed'])
        for response in [b'<broken', w.Fault('http_403')]:
            kwargs={'side_effect':response} if isinstance(response,Exception) else {'return_value':response}
            with patch.object(w,'request',**kwargs),patch.object(w.time,'time',return_value=NOW+1000):
                w.run_once(self.storage,'synthetic-key',self.translator)
            self.assertEqual(self.storage.load()['observed'],original)
        self.assertFalse(self.storage.load()['pending']);self.translator.assert_not_called()
    def test_oversize_retained_no_truncation(self):
        self.baseline();self.translator.side_effect=ValueError()
        text='🌕完整'*4000
        self.poll(item(),item('b',body=text))
        self.assertEqual(self.sent,[]);job=self.s['pending']['b']
        self.assertEqual(job['payload']['body'],text);self.assertEqual(job['error'],'payload_too_large')
    def test_oversize_translation_retained(self):
        self.baseline();self.translator.return_value={'title':'标题','body':'🌕'*4000};self.new()
        self.assertEqual(self.sent,[]);self.assertEqual(self.s['pending']['b']['translation'],'translated')
    def test_bad_link_only_changes_click(self):
        self.baseline();self.translator.side_effect=ValueError()
        self.poll(item(),item('b',link='javascript:alert(1)',body='Keep ALL original commentary.'))
        self.assertEqual(self.sent[0],{'title':'Codex reset','body':'Keep ALL original commentary.','url':w.HOME_URL})
    def test_no_key_keeps_selected_payload(self):
        self.baseline();self.new(key='');self.assertEqual(len(self.s['pending']),1)
        self.assertEqual(self.s['pending']['b']['selection'],'selected');self.assertEqual(self.translator.call_count,1)
        self.new(now=NOW+1);self.assertEqual(len(self.sent),1);self.assertEqual(self.translator.call_count,1)
    def test_empty_feed_guard(self):
        self.baseline()
        with patch.object(w,'request',return_value=feed()),patch.object(w.time,'time',return_value=NOW+1):
            s=w.run_once(self.storage,'',self.translator)
        self.assertEqual(s['health']['reason'],'unexpected_empty_feed');self.assertEqual(s['observed'],self.s['observed'])
    def test_source_retry_after(self):
        self.baseline()
        with patch.object(w,'request',side_effect=w.Fault('http_429',7200)) as request,patch.object(w.time,'time',return_value=NOW):
            w.run_once(self.storage,'',self.translator);w.run_once(self.storage,'',self.translator)
            self.assertEqual(request.call_count,1)
    def test_no_local_source_notifications(self):
        self.baseline()
        with patch.object(w,'request',side_effect=w.Fault('http_500')),patch.object(w.time,'time',return_value=NOW+86400),patch.object(w,'push') as push:
            s=w.run_once(self.storage,'synthetic-key',self.translator);push.assert_not_called()
        self.assertEqual(s['health']['reason'],'http_500')
    def test_translation_crash_uses_persisted_english(self):
        self.baseline();self.translator.side_effect=SystemExit()
        with self.assertRaises(SystemExit):self.new()
        self.s=self.storage.load();self.translator.side_effect=None;self.new(now=NOW+1)
        self.assertEqual(self.translator.call_count,1);self.assertEqual(self.sent[0]['body'],item()['body'])
    def test_batch_bound_no_alert_loss(self):
        self.baseline();items=[item(chr(98+i)) for i in range(7)]
        self.poll(item(),*items);self.assertEqual(len(self.sent),5);self.assertEqual(len(self.s['pending']),2)
        self.poll(item(),*items,now=NOW+1);self.assertEqual(len(self.sent),7);self.assertEqual(self.translator.call_count,7)
    def test_pending_old_content_superseded(self):
        self.baseline();self.new(fail=True)
        self.poll(item(),item('b',body='changed'))
        self.assertEqual(self.translator.call_count,2);self.assertEqual(len(self.sent),1)
    def test_disabled_translation(self):
        with patch.dict(w.os.environ,{'TIBOWATCH_TRANSLATE':'0'}):self.baseline();self.new()
        self.translator.assert_not_called();self.assertEqual(self.sent[0]['body'],item()['body'])
    def test_backup_and_lock(self):
        with w.State(self.temp.name) as storage:
            storage.save(self.s);storage.save(self.s);storage.path.write_text('{')
            self.assertEqual(storage.load(),self.s)
            with self.assertRaises(w.Fault):
                with w.State(self.temp.name):pass
            storage.backup.write_text('{')
            with self.assertRaises(w.Fault):storage.load()
    def test_v1_migration_no_replay_test_preserved(self):
        old=w.blank();old.update(version=1,initialized=True,test_push='accepted_by_push_service',observed={'legacy':{'headline':'old'}})
        self.storage.save(old)
        with patch.object(w,'request',return_value=feed(item())),patch.object(w.time,'time',return_value=NOW):
            new=w.run_once(self.storage,'',self.translator)
        self.assertEqual(new['version'],2);self.assertFalse(new['pending']);self.translator.assert_not_called()
        self.assertEqual(new['test_push'],'accepted_by_push_service')
        with patch.object(w,'request',return_value=feed(item())),patch.object(w.time,'time',return_value=NOW+1):
            again=w.run_once(self.storage,'',self.translator)
        self.assertFalse(again['pending']);self.translator.assert_not_called()
        self.assertEqual(json.loads((Path(self.temp.name)/'state.v1-backup.json').read_text()),old)
    def test_v1_pending_blocks_migration(self):
        old=w.blank();old.update(version=1,pending={'business':{'item':'preserve'}});self.storage.save(old)
        with self.assertRaises(w.Fault):w.run_once(self.storage,'',self.translator)
        self.assertEqual(self.storage.load(),old);self.translator.assert_not_called()
    def test_v1_bad_source_does_not_migrate(self):
        old=w.blank();old['version']=1;self.storage.save(old)
        with patch.object(w,'request',return_value=b'bad'):
            result=w.run_once(self.storage,'',self.translator)
        self.assertEqual(result['version'],1);self.assertFalse((Path(self.temp.name)/'state.v1-backup.json').exists())
    def test_installation_test_not_resent(self):
        self.s['test_push']='accepted_by_push_service';self.storage.save(self.s)
        with patch.object(sys,'argv',['watcher','test-push','--state-dir',self.temp.name]),patch.dict(w.os.environ,{'BARK_KEY':'synthetic-key'}),patch.object(w,'push') as push:
            w.main();push.assert_not_called()
    def test_dry_run_no_files_or_translation(self):
        with patch.object(sys,'argv',['watcher','dry-run','--state-dir',self.temp.name]),patch.object(w,'request',return_value=feed(item())),patch.object(w.time,'time',return_value=NOW),patch.object(w,'translate') as translate:
            w.main();translate.assert_not_called()
        self.assertEqual(list(Path(self.temp.name).iterdir()),[])

class ParsingAndTransport(unittest.TestCase):
    def test_exact_xml_text(self):
        x=item(title='  Codex & Astra  ',body='<p>Use all quota.</p>\nNext line!')
        result=w.parse_rss(feed(x),NOW)[0]
        self.assertEqual((result['title'],result['body']),(x['title'],x['body']))
    def test_dtd_rejected(self):
        for raw in [b'<!DOCTYPE rss><rss/>', '<!DOCTYPE rss><rss/>'.encode('utf-16')]:
            with self.assertRaises(w.Fault):w.parse_rss(raw,NOW)
    def test_bad_dates_and_structure(self):
        for raw in [b'<html/>',feed(item()).replace(b'<guid>a</guid>',b''),feed(item()).replace(b'<pubDate>',b'<pubDate>invalid ')]:
            with self.assertRaises(w.Fault):w.parse_rss(raw,NOW)
    def test_conflicting_guid(self):
        with self.assertRaises(w.Fault):w.parse_rss(feed(item(),item(body='other')),NOW)
    def test_click_urls(self):
        for u in ['http://example.org','javascript:a','https://user:pass@example.org','https://','https://example.org/\n']:
            self.assertEqual(w.click_url(u),w.HOME_URL)
        self.assertEqual(w.click_url('https://example.org:8443/a?q=b'),'https://example.org:8443/a?q=b')
    def test_response_size_and_secret_redaction(self):
        class Response(BytesIO):status=200
        with patch.object(w.urllib.request.OpenerDirector,'open',return_value=Response(b'a'*(w.LIMIT+1))):
            with self.assertRaises(w.Fault):w.request(w.SOURCE)
        with patch.object(w.urllib.request.OpenerDirector,'open',side_effect=w.urllib.error.URLError('synthetic-secret')):
            with self.assertRaises(w.Fault) as e:w.request(w.ENDPOINT,b'{}')
            self.assertNotIn('synthetic-secret',str(e.exception))
    def test_bark_success_contract(self):
        for raw in [b'<html>',b'{"code":500}',b'{"code":"200"}',b'[]']:
            with patch.object(w,'request',return_value=raw):
                with self.assertRaises(w.Fault):w.push({'title':'a','body':'b','url':w.HOME_URL},'k')
        with patch.object(w,'request',return_value=b'{"code":200}'):
            w.push({'title':'a','body':'b','url':w.HOME_URL},'k')
    def test_retry_after_and_redirect(self):
        self.assertEqual(w.retry_after('7200',NOW),7200);self.assertEqual(w.retry_after('bad',NOW),0)
        self.assertIsNone(w.NoRedirect().redirect_request(None,None,302,'',{},'https://example.org'))

class CodexInvocation(unittest.TestCase):
    def fake_process(self, args, **kwargs):
        self.args,self.kwargs=args,kwargs
        output=Path(args[args.index('--output-last-message')+1])
        process=Mock();process.returncode=0;process.poll.return_value=0
        def communicate(data,timeout):
            self.input,self.timeout=data,timeout
            output.write_bytes(self.output)
        process.communicate.side_effect=communicate
        return process
    def test_single_small_model_safe_stdin(self):
        self.output='{"title":"Codex 重置","body":"全部内容"}'.encode()
        with patch.object(w.subprocess,'Popen',side_effect=self.fake_process) as popen,patch.dict(w.os.environ,{'BARK_KEY':'synthetic-secret'}):
            value=w.translate('$(not-a-command)','body; ignored shell')
        self.assertEqual(value['body'],'全部内容');self.assertEqual(popen.call_count,1)
        self.assertEqual(self.args[self.args.index('--model')+1],'gpt-5.6-luna')
        self.assertNotIn('$(not-a-command)',self.args);self.assertIn(b'$(not-a-command)',self.input)
        self.assertNotIn('BARK_KEY',self.kwargs['env']);self.assertTrue(self.kwargs['start_new_session'])
        self.assertEqual(self.timeout,30);self.assertNotIn('shell',self.kwargs)
    def test_invalid_cli_output(self):
        for raw in [b'not json',b'{"title":"x","body":"y","extra":1}',b'{"title":"x","body":"y","body":"z"}',b'{"title":1,"body":"x"}']:
            self.output=raw
            with patch.object(w.subprocess,'Popen',side_effect=self.fake_process) as popen:
                with self.assertRaises(w.Fault):w.translate('title','body')
                self.assertEqual(popen.call_count,1)
    def test_cli_unavailable_no_other_model(self):
        with patch.object(w.subprocess,'Popen',side_effect=FileNotFoundError()) as popen:
            with self.assertRaises(w.Fault):w.translate('title','body')
            self.assertEqual(popen.call_count,1)
    def test_timeout_kills_process_group(self):
        process=Mock();process.pid=12345;process.poll.return_value=None
        process.communicate.side_effect=subprocess.TimeoutExpired('codex',8)
        with patch.object(w.subprocess,'Popen',return_value=process) as popen,patch.object(w.os,'killpg') as kill:
            with self.assertRaises(w.Fault):w.translate('title','body')
            kill.assert_called_once_with(12345,w.signal.SIGKILL);self.assertEqual(popen.call_count,1)

if __name__=='__main__':unittest.main()
