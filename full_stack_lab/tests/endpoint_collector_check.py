"""Collector control/partial-report regressions; synthetic data, no live MCP or DB."""
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('endpoint_collector', Path(__file__).resolve().parents[2]/'endpoint-agent/agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class Collector(unittest.TestCase):
    def setUp(self):
        agent.SCAN_ERRORS.clear()
        self.finding = {'source':'stdio-process','address':'local-process','port':None,
                        'process_name':'ghidramcp','command_line':agent.command_digest('ghidramcp --token fixture-secret'),
                        'mcp_evidence':'suspected'}

    def test_process_only_reports_without_network_policy_or_probe(self):
        posted=[]
        with patch.object(agent,'PROCESS_ENABLED',True), patch.object(agent,'SCAN_ENABLED',False), \
             patch.object(agent,'stdio_processes',return_value=[self.finding]), \
             patch.object(agent,'call',side_effect=lambda method,path,body=None: posted.append((method,path,body)) or {'accepted':1}), \
             patch.object(agent,'probe_mcp',side_effect=AssertionError('process scan must not contact sockets')):
            result=agent.report_processes()
            disabled=agent.report_listeners()
        self.assertEqual(result['state'],'success')
        self.assertEqual(disabled['state'],'disabled')
        self.assertEqual(len(posted),1)
        self.assertEqual(posted[0][1],'/api/endpoint/listeners')
        self.assertEqual(posted[0][2]['sources'],['stdio-process'])
        self.assertIs(posted[0][2]['complete'],True)
        self.assertNotIn('fixture-secret',json.dumps(posted))

    def test_overflow_report_is_partial_and_cannot_reconcile_all_rows(self):
        posted=[]
        with patch.object(agent,'PROCESS_ENABLED',True), patch.object(agent,'stdio_processes',return_value=[self.finding]*501), \
             patch.object(agent,'call',side_effect=lambda method,path,body=None: posted.append(body) or {'accepted':500}):
            result=agent.report_processes()
        self.assertEqual(len(posted[0]['findings']),500)
        self.assertIs(posted[0]['complete'],False)
        self.assertEqual(result['state'],'partial')

    def test_unreadable_process_source_preserves_partial_not_successful_empty(self):
        def partial():
            agent.SCAN_ERRORS.add('process_unreadable')
            return []
        posted=[]
        with patch.object(agent,'PROCESS_ENABLED',True), patch.object(agent,'stdio_processes',side_effect=partial), \
             patch.object(agent,'call',side_effect=lambda method,path,body=None: posted.append(body) or {'accepted':0}):
            result=agent.report_processes()
        self.assertIs(posted[0]['complete'],False)
        self.assertEqual(result['state'],'partial')

    def test_invalid_config_is_not_a_complete_empty_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'.mcp.json';p.write_text('{invalid',encoding='utf-8')
            posted=[]
            with patch.object(agent,'SCAN_PATHS',[Path(folder)]), \
                 patch.object(agent,'call',side_effect=lambda method,path,body=None: posted.append(body) or {'accepted':0}):
                result=agent.report_configs()
        self.assertIs(posted[0]['complete'],False)
        self.assertEqual(result['state'],'partial')

    def test_other_uid_process_is_excluded_and_matching_uid_command_is_hashed(self):
        class Pid:
            def __init__(self,name,uid):self.name,self.uid=name,uid
            def stat(self):return SimpleNamespace(st_uid=self.uid)
            def __truediv__(self,name):return self
            def read_bytes(self):return b'/opt/ghidramcp\x00--token\x00fixture-secret'
            def read_text(self,errors=None):
                return '0::/system.slice/docker-'+'c'*64+'.scope' if self.name=='333' else '0::/user.slice'
        labelled=SimpleNamespace(stdout='1\n')  # the local runner's container for an approved MCP (mcpgw.local=1)
        with patch.object(agent.platform,'system',return_value='Linux'), \
             patch.object(agent,'PROCESS_UID','1001'), \
             patch.object(agent.os.path,'isfile',return_value=True), \
             patch.object(agent.subprocess,'run',return_value=labelled), \
             patch.object(agent.Path,'iterdir',return_value=iter([Pid('111',1000),Pid('222',1001),Pid('333',1001)])):
            rows=agent.stdio_processes()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['process_name'],'ghidramcp')
        self.assertTrue(rows[0]['command_line'].startswith('sha256:'))
        self.assertNotIn('fixture-secret',json.dumps(rows))

    def test_failed_inventory_does_not_suppress_process_channel(self):
        failure=urllib.error.HTTPError('https://fixture.invalid',503,'fixture failure',{},None)
        status=[]
        out=io.StringIO()
        with patch.object(agent,'report_configs',side_effect=failure), \
             patch.object(agent,'report_processes',return_value={'state':'success','accepted':1}), \
             patch.object(agent,'report_listeners',return_value={'state':'disabled','accepted':0}), \
             patch.object(agent,'report_status',side_effect=lambda *args: status.append(args)),redirect_stdout(out):
            result=agent.once()
        self.assertEqual(result['inventory']['state'],'failed')
        self.assertEqual(result['process']['state'],'success')
        self.assertEqual(result['network']['state'],'disabled')
        self.assertEqual(len(status),3)
        self.assertEqual(json.loads(out.getvalue())['observation'],result)

    def test_harness_prompt_is_not_socket_evidence_but_initialize_is(self):
        row = {'address': '127.0.0.1', 'port': 54321, 'process_name': 'claude',
               'command_line': '/opt/claude -p "fastmcp modelcontextprotocol"'}
        for enabled in (False, True):
            with self.subTest(probe=enabled), patch.object(agent, 'local_listeners', return_value=[row]), \
                 patch.object(agent, 'probe_mcp', return_value=None):
                self.assertEqual(agent.listener_findings({'probe_mcp': enabled}), [])
        with patch.object(agent, 'local_listeners', return_value=[row]), \
             patch.object(agent, 'probe_mcp', return_value={'server_name': 'fixture'}):
            self.assertEqual(agent.listener_findings({})[0]['mcp_evidence'], 'confirmed')

    def test_real_server_commands_are_still_reported_on_process_and_socket_paths(self):
        commands = ['python -m fastmcp run server.py', 'npx -y @modelcontextprotocol/server-filesystem /docs']
        for command in commands:
            with self.subTest(command=command), patch.object(agent.platform, 'system', return_value='Windows'), \
                 patch.object(agent, '_windows_processes', return_value={'123': ('server', command)}):
                self.assertEqual(agent.stdio_processes()[0]['mcp_evidence'], 'suspected')
            row = {'address': '127.0.0.1', 'port': 54321, 'command_line': command}
            with patch.object(agent, 'local_listeners', return_value=[row]):
                self.assertEqual(agent.listener_findings({'probe_mcp': False})[0]['mcp_evidence'], 'suspected')

    def test_quoted_node_harness_prompt_is_not_a_stdio_server(self):
        command = r'"C:\Program Files\nodejs\node.exe" "C:\Program Files\nodejs\node_modules\@openai\codex\bin\codex.js" exec "fastmcp"'
        with patch.object(agent.platform, 'system', return_value='Windows'), \
             patch.object(agent, '_windows_processes', return_value={'123': ('node.exe', command)}):
            self.assertEqual(agent.stdio_processes(), [])

    def test_listener_permission_and_policy_disabled_are_distinct(self):
        with patch.object(agent,'SCAN_ENABLED',True), patch.object(agent,'call',side_effect=urllib.error.HTTPError(
                'https://fixture.invalid',403,'denied',{},None)):
            self.assertEqual(agent.report_listeners()['state'],'unauthorized')
        with patch.object(agent,'SCAN_ENABLED',True), patch.object(agent,'call',return_value={'enabled':False}):
            self.assertEqual(agent.report_listeners()['error_code'],'policy_disabled')

    def test_once_exit_keeps_partial_telemetry_but_fails_delivery_and_authorization(self):
        for state, expected in (('partial', 0), ('failed', 1), ('unauthorized', 1)):
            statuses = []
            output = io.StringIO()
            with self.subTest(state=state), patch.object(agent, 'DEVICE_KEY', 'fixture'), \
                 patch.object(agent, 'validate_gateway'), patch.object(agent, 'enroll'), \
                 patch.object(agent, 'log'), patch.object(agent, 'endpoint_id', return_value='fixture'), \
                 patch.object(agent, 'ONE_SHOT', True), patch.object(agent, 'CONFIG', {}), \
                 patch.object(agent, 'report_configs', return_value={'state': 'success', 'accepted': 1}), \
                 patch.object(agent, 'report_processes', return_value={'state': state, 'accepted': 0}), \
                 patch.object(agent, 'report_listeners', return_value={'state': 'disabled'}), \
                 patch.object(agent, 'report_status', side_effect=lambda *args: statuses.append(args)), redirect_stdout(output):
                self.assertEqual(agent.main(), expected)
            self.assertEqual(json.loads(output.getvalue())['observation']['process']['state'], state)
            self.assertEqual(statuses[1], ('process', state, 0, 'incomplete_snapshot' if state == 'partial' else ''))

    def test_device_credential_redirects_are_refused(self):
        self.assertIsNone(agent.NoRedirect().redirect_request(None,302,'redirect',{},'https://other.invalid'))


if __name__=='__main__':
    unittest.main(verbosity=2)
