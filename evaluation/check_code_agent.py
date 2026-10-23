"""Isolated-code contracts, simulated transport, trusted guest fixtures and real SQL/API checks.

Only fixed, authored fixture programs run on the test host. Generated model code
always uses a mocked isolation transport in tests; production has no host path.
"""
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch, Mock
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend.agents import sandbox
from backend.agents.contracts import Decision, RunInput, allowed_tools
from backend.agents.planning import current_tools, compact_observations
from backend.agents.routes import install_agents, public_run
from backend.agents.runtime import run_agent
from backend.agents.store import RunStopped
from backend.auth_routes import get_current_student
from evaluation import check_agents as fixtures


def req(**kwargs):
    return RunInput(course_id=3, skill='code_analysis', goal='Calculate a CSV mean', **kwargs)


def code_action(code='print(4)', outputs=None):
    return fixtures.action('code_execute', title='Calculate', code=code, outputs=outputs or [])


def guest_result(exit_code=0, stdout='4\n', artifacts=None, timed_out=False):
    return json.dumps(dict(exit_code=exit_code, stdout=stdout, stderr='', timed_out=timed_out,
        stdout_truncated=False, stderr_truncated=False, artifacts=artifacts or []))


def observed(exit_code=0, outputs=None):
    files = [{'name': 'result.csv', 'data': base64.b64encode(b'value\n4\n').decode()}] if outputs else []
    return sandbox.parse_result(guest_result(exit_code, artifacts=files), 'print(4)', outputs or [])


class CodeContracts(unittest.TestCase):
    def test_inputs_are_small_csv_and_cannot_be_attached_to_other_skills(self):
        good = {'name': 'data.csv', 'text': 'a\n1\n'}
        self.assertEqual(req(inputs=[good]).inputs[0].name, 'data.csv')
        for inputs in ([{**good, 'name': '../data.csv'}], [{**good, 'name': 'data.py'}],
                       [{**good, 'text': '界'*6000}], [{**good, 'text': 'a\0b'}],
                       [good, {**good, 'name': 'DATA.csv'}], [good]*3):
            with self.subTest(inputs=str(inputs)[:60]), self.assertRaises(ValueError): req(inputs=inputs)
        with self.assertRaises(ValueError): RunInput(course_id=3, skill='study_plan', goal='Plan', inputs=[good])

    def test_execution_requires_enabled_backend_and_cannot_finish_without_execution(self):
        with patch('backend.agents.sandbox.backend_name', return_value='docker'):
            permitted = allowed_tools(req(allow_memory_write=True))
        self.assertEqual(permitted, {'document_search', 'code_execute', 'finish'})
        self.assertEqual(current_tools(req(), permitted, [], 8), {'code_execute'})
        trace = [{'tool': 'code_execute'}]*2
        self.assertEqual(current_tools(req(), permitted, trace, 4), {'finish'})
        with patch.dict(os.environ, {'AURA_CODE_BACKEND': 'disabled'}):
            self.assertIsNone(sandbox.backend_name())
            self.assertNotIn('code_execute', allowed_tools(req()))
        for name in ['../bad.csv', 'bad.html', 'bad.svg', '/tmp/x.json']:
            with self.assertRaises(ValueError): Decision.model_validate(code_action(outputs=[name]))
        with self.assertRaises(ValueError): Decision.model_validate(code_action(outputs=['same.csv']*2))

    def test_result_validation_and_model_context_strip_binary_bytes(self):
        out = observed(outputs=['result.csv'])
        self.assertEqual(out['status'], 'succeeded')
        self.assertEqual(out['artifacts'][1]['size'], 8)
        self.assertEqual(len(out['artifacts'][1]['sha256']), 64)
        context = compact_observations([{'tool': 'code_execute', 'data': out}])
        self.assertNotIn('data', context[0]['data']['artifacts'][0])
        self.assertTrue(context[0]['untrusted_data'])
        for raw in ['{}', guest_result(artifacts=[{'name': '../result.csv', 'data': ''}]),
                    guest_result(artifacts=[{'name': 'result.csv', 'data': '!'}]),
                    guest_result(artifacts=[{'name': 'result.csv', 'data': base64.b64encode(b'x'*131073).decode()}])]:
            with self.assertRaises(sandbox.SandboxUnavailable): sandbox.parse_result(raw, 'print(4)', ['result.csv'])
        self.assertEqual([i['name'] for i in observed(exit_code=1, outputs=['result.csv'])['artifacts']], ['program.py'])

    def test_explanation_context_marks_its_own_truncation_without_mutating_saved_output(self):
        output=sandbox.parse_result(guest_result(stdout='a'*5000), 'print(4)', [])
        output['stderr']='e'*5000
        observation={'tool':'code_execute','data':output,'executed_program':'# program\n'+'p'*6500}
        before=copy.deepcopy(observation)
        compact=compact_observations([observation])[0]
        self.assertEqual(len(compact['executed_program']),6000)
        self.assertTrue(compact['program_truncated']);self.assertTrue(compact['untrusted_data'])
        self.assertEqual(len(compact['data']['stdout']),4096)
        self.assertEqual(len(compact['data']['stderr']),4096)
        self.assertTrue(compact['data']['stdout_truncated']);self.assertTrue(compact['data']['stderr_truncated'])
        self.assertNotIn('data',compact['data']['artifacts'][0])
        repeated=compact_observations([compact])[0]
        self.assertTrue(repeated['program_truncated']);self.assertTrue(repeated['data']['stdout_truncated'])
        self.assertEqual(observation,before)
        output['stdout']='short';output['stderr']='';output['stdout_truncated']=True
        compact=compact_observations([{'tool':'code_execute','data':output,'executed_program':'print(4)'}])[0]
        self.assertTrue(compact['data']['stdout_truncated']) # preserve guest-side truncation too
        self.assertFalse(compact['data']['stderr_truncated']);self.assertFalse(compact['program_truncated'])


class SandboxTransport(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'AURA_CODE_BACKEND': 'nebius', 'NEBIUS_API_KEY': 'private-test-key',
            'NEBIUS_PROJECT_ID': 'project_test', 'NEBIUS_SANDBOX_IMAGE': str(uuid4())})
        self.env.start(); self.addCleanup(self.env.stop)
        cli = patch('backend.agents.sandbox.shutil.which', return_value='/test/docker'); cli.start(); self.addCleanup(cli.stop)

    def success(self, identity):
        return {'uuid': identity, 'status': 'SUCCESS', 'metadata': {'result': {
            'state': {'exit_code': 0, 'timed_out': False},
            'stdout': {'value': guest_result(), 'encoding': 'utf-8', 'truncated': False}}}}

    def test_nebius_uses_disposable_offline_guest_and_real_process_result(self):
        identity = str(uuid4()); started = []
        with patch.object(sandbox, '_http', side_effect=[{'uuid': identity}, self.success(identity)]) as http:
            out = sandbox.execute('print(4)', [], {'data.csv': 'a\n1'}, run_id=uuid4(), attempt=1,
                seconds=30, check_active=lambda: None, on_start=started.append)
        self.assertEqual(out['status'], 'succeeded')
        payload = http.call_args_list[0].kwargs['json']
        self.assertFalse(payload['networking']['enabled']); self.assertFalse(payload['shell'])
        self.assertTrue(payload['disposable']); self.assertFalse(payload['preserve_env'])
        self.assertEqual(payload['uid'], 65534); self.assertEqual(payload['timeout'], 20)
        self.assertNotIn('private-test-key', json.dumps(payload))
        data = json.loads(base64.b64decode(payload['stdin']['value']))
        self.assertEqual(data['files'], {'data.csv': 'a\n1'})
        self.assertEqual(started[0]['id'], identity)
        bad = self.success(identity); bad['metadata']['result']['state']['exit_code'] = 1
        with patch.object(sandbox, '_http', side_effect=[{'uuid': identity}, bad]), self.assertRaises(sandbox.SandboxUnavailable):
            sandbox._nebius({}, time.monotonic()+30, lambda: None, lambda handle: None)

    def test_uncertain_post_is_never_repeated_or_failed_over(self):
        with patch.object(sandbox, '_http', side_effect=sandbox.SandboxUnavailable('runtime_unavailable')) as http, patch.object(sandbox, '_docker') as docker:
            with self.assertRaises(sandbox.SandboxUnavailable) as error:
                sandbox.execute('print(4)', [], {}, run_id=uuid4(), attempt=1, seconds=30, check_active=lambda: None, on_start=lambda h: None)
        self.assertEqual(error.exception.code, 'submission_uncertain')
        self.assertEqual(http.call_count, 1); docker.assert_not_called()

    def test_cancel_after_acceptance_cleans_known_operation(self):
        identity = str(uuid4())
        with patch.object(sandbox, '_http', return_value={'uuid': identity}), patch.object(sandbox, 'cleanup') as cleanup:
            with self.assertRaises(RunStopped):
                sandbox._nebius({}, time.monotonic()+30, lambda: None, lambda handle: (_ for _ in ()).throw(RunStopped()))
        cleanup.assert_called_once_with({'backend': 'nebius', 'id': identity})

    def test_http_auth_stays_in_headers_and_disallows_redirects(self):
        reply = Mock(status_code=200); reply.iter_content.return_value = [b'{"ok":true}']
        context = Mock(); context.__enter__ = Mock(return_value=reply); context.__exit__ = Mock(return_value=False)
        with patch('backend.agents.sandbox.requests.request', return_value=context) as transport:
            self.assertEqual(sandbox._http('POST', '/instances', time.monotonic()+10, json={'safe': True}), {'ok': True})
        self.assertFalse(transport.call_args.kwargs['allow_redirects'])
        self.assertEqual(transport.call_args.kwargs['headers']['Project'], 'project_test')
        self.assertEqual(transport.call_args.kwargs['json'], {'safe': True})
        with patch('backend.agents.sandbox.requests.request', side_effect=requests.Timeout('private')) as transport:
            with self.assertRaises(sandbox.SandboxUnavailable) as error: sandbox._http('POST', '/instances', time.monotonic()+5)
        self.assertNotIn('private', str(error.exception)); self.assertEqual(transport.call_count, 1)

    def test_remote_truncated_stream_is_never_parsed_as_success(self):
        with self.assertRaises(sandbox.SandboxUnavailable): sandbox._stream_text({'truncated': True, 'encoding': 'utf-8', 'value': '{}'})
        identity = str(uuid4())
        with patch.object(sandbox, '_http', side_effect=[{'status': 'EXECUTING'}, {}]) as http:
            self.assertFalse(sandbox.cleanup({'backend': 'nebius', 'id': identity}))
        self.assertEqual(http.call_args_list[-1].args[0], 'DELETE')

    def test_docker_uses_pinned_local_image_no_mounts_and_restricted_environment(self):
        image = {'Os': 'linux', 'Id': 'sha256:'+'a'*64, 'Config': {'Env': ['PATH=/usr/local/bin:/usr/bin'], 'Volumes': None}}
        inspected = Mock(returncode=0, stdout=json.dumps([image]).encode())
        def spawn(args, **kwargs):
            self.assertIn('--network=none', args); self.assertIn('--read-only', args)
            self.assertIn('--cap-drop=ALL', args); self.assertIn('--security-opt=no-new-privileges:true', args)
            self.assertIn('--pull=never', args); self.assertIn(image['Id'], args)
            self.assertIn('--user=65534:65534', args); self.assertIn('--pids-limit=64', args)
            self.assertFalse(any(arg in ('-v', '--volume', '--mount', '--privileged') for arg in args))
            self.assertNotIn('NEBIUS_API_KEY', kwargs['env'])
            self.assertEqual(json.load(kwargs['stdin'])['code'], 'print(4)')
            kwargs['stdout'].write(guest_result().encode())
            return Mock(returncode=0, poll=lambda: 0)
        with patch.object(sandbox, '_docker_control', return_value=inspected), patch.object(sandbox, 'cleanup') as cleanup, patch('backend.agents.sandbox.subprocess.Popen', side_effect=spawn):
            raw = sandbox._docker({'code': 'print(4)'}, time.monotonic()+30, lambda: None, lambda handle: None, 'aura-code-'+'a'*32+'-1')
        self.assertEqual(json.loads(raw)['stdout'], '4\n'); cleanup.assert_called_once()
        image['Config']['Volumes'] = {'/data': {}}
        with patch.object(sandbox, '_docker_control', return_value=Mock(returncode=0, stdout=json.dumps([image]).encode())), patch.object(sandbox, 'cleanup'), patch('backend.agents.sandbox.subprocess.Popen') as proc:
            with self.assertRaises(sandbox.SandboxUnavailable): sandbox._docker({}, time.monotonic()+30, lambda: None, lambda h: None, 'aura-code-'+'a'*32+'-1')
        proc.assert_not_called()

    def test_docker_deadline_kills_client_and_cleans_container(self):
        image = {'Os': 'linux', 'Id': 'sha256:'+'a'*64, 'Config': {'Env': []}}
        proc = Mock(returncode=None); proc.poll.return_value = None
        with patch.object(sandbox, '_docker_control', return_value=Mock(returncode=0, stdout=json.dumps([image]).encode())), patch.object(sandbox, 'cleanup') as cleanup, patch('backend.agents.sandbox.subprocess.Popen', return_value=proc):
            with self.assertRaises(sandbox.SandboxUnavailable) as error:
                sandbox._docker({}, time.monotonic()-1, lambda: None, lambda h: None, 'aura-code-'+'a'*32+'-1')
        self.assertEqual(error.exception.code, 'execution_timeout')
        cleanup.assert_called_once(); proc.kill.assert_called_once()

    def test_http_oversize_response_and_invalid_cleanup_handles_are_bounded(self):
        reply = Mock(status_code=200); reply.iter_content.return_value = [b'x'*(sandbox.MAX_HTTP_RESPONSE+1)]
        context = Mock(); context.__enter__ = Mock(return_value=reply); context.__exit__ = Mock(return_value=False)
        with patch('backend.agents.sandbox.requests.request', return_value=context), self.assertRaises(sandbox.SandboxUnavailable):
            sandbox._http('GET', '/operations/test', time.monotonic()+5)
        with patch.object(sandbox, '_docker_control') as docker, patch.object(sandbox, '_http') as http:
            self.assertFalse(sandbox.cleanup({'backend': 'docker', 'id': 'another-users-container'}))
            self.assertFalse(sandbox.cleanup({'backend': 'nebius', 'id': '../anything'}))
        docker.assert_not_called(); http.assert_not_called()

    def test_docker_setup_failures_keep_specific_codes_without_raw_messages(self):
        failures = [
            (Mock(returncode=1, stdout=b'', stderr=b'error during connect: private pipe path'), 'docker_daemon_unavailable'),
            (Mock(returncode=1, stdout=b'[]', stderr=b'Error: No such image: private-image'), 'docker_image_missing'),
            (Mock(returncode=1, stdout=b'', stderr=b'private unknown detail'), 'docker_launch_failed'),
            (Mock(returncode=0, stdout=b'[{"Os":"windows"}]'), 'docker_requires_linux'),
            (Mock(returncode=0, stdout=b'not json private'), 'docker_launch_failed'),
        ]
        for reply, code in failures:
            with self.subTest(code=code), patch.object(sandbox, '_docker_control', return_value=reply), self.assertRaises(sandbox.SandboxUnavailable) as caught:
                sandbox.inspect_docker_image()
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('private', str(caught.exception))
        with patch('backend.agents.sandbox.shutil.which', return_value=None), self.assertRaises(sandbox.SandboxUnavailable) as caught:
            sandbox.inspect_docker_image()
        self.assertEqual(caught.exception.code, 'docker_cli_unavailable')
        with patch.object(sandbox, '_docker_control', side_effect=subprocess.TimeoutExpired('private', 5)), self.assertRaises(sandbox.SandboxUnavailable) as caught:
            sandbox.inspect_docker_image()
        self.assertEqual(caught.exception.code, 'docker_daemon_unavailable')

    def test_docker_exit_failure_captures_only_classified_reason(self):
        image = {'Os': 'linux', 'Id': 'sha256:'+'a'*64, 'Config': {'Env': []}}
        def spawn(args, **kw):
            kw['stderr'].write(b'private contents: error during connect')
            return Mock(returncode=125, poll=lambda: 125)
        with patch.object(sandbox, '_docker_control', return_value=Mock(returncode=0, stdout=json.dumps([image]).encode())), patch.object(sandbox, 'cleanup'), patch('backend.agents.sandbox.subprocess.Popen', side_effect=spawn), self.assertRaises(sandbox.SandboxUnavailable) as caught:
            sandbox._docker({}, time.monotonic()+10, lambda: None, lambda h: None, 'aura-code-'+'a'*32+'-1')
        self.assertEqual(caught.exception.code, 'docker_daemon_unavailable')
        self.assertNotIn('private', str(caught.exception))

    def test_host_docker_environment_preserves_context_and_windows_setup_without_app_keys(self):
        configured = {'DOCKER_CONTEXT': 'desktop-linux', 'DOCKER_CONFIG': '/operator/docker-config',
            'DOCKER_HOST': 'npipe:////./pipe/dockerDesktopLinuxEngine', 'DOCKER_CERT_PATH': '/operator/certs',
            'DOCKER_TLS_VERIFY': '1', 'DOCKER_API_VERSION': '1.56', 'TEMP': '/operator/temp',
            'TMP': '/operator/tmp', 'Path': '/operator/bin', 'SystemRoot': '/operator/windows',
            'NEBIUS_API_KEY': 'must-not-leak', 'DB_PASSWORD': 'must-not-leak', 'AUTH_JWT_SECRET': 'must-not-leak'}
        with patch.dict(os.environ, configured, clear=True):
            env = sandbox._docker_env()
        for key in configured:
            if key in {'NEBIUS_API_KEY', 'DB_PASSWORD', 'AUTH_JWT_SECRET'}: self.assertNotIn(key, env)
            else: self.assertEqual(env[key], configured[key])

    def test_actual_cli_subprocess_receives_context_and_temp_settings(self):
        # Fixed trusted fixture replaces only the Docker executable in this test.
        # No model-produced program is executed on the host.
        original_run = subprocess.run
        source = "import os,json; assert os.environ['DOCKER_CONTEXT']=='desktop-linux'; assert os.environ['TEMP']=='operator-temp'; assert 'NEBIUS_API_KEY' not in os.environ; print(json.dumps([{'Os':'linux','Id':'sha256:'+'a'*64,'Config':{'Env':[]}}]))"
        def cli(args, **kwargs):
            self.assertEqual(args[1:3], ['image', 'inspect'])
            return original_run([sys.executable, '-I', '-c', source], **kwargs)
        with patch.dict(os.environ, {'DOCKER_CONTEXT': 'desktop-linux', 'TEMP': 'operator-temp', 'NEBIUS_API_KEY': 'must-not-leak'}), patch('backend.agents.sandbox.subprocess.run', side_effect=cli):
            self.assertEqual(sandbox.inspect_docker_image(), 'sha256:'+'a'*64)

    def test_context_settings_are_not_forwarded_into_the_container(self):
        image_id = 'sha256:'+'a'*64
        def spawn(args, **kwargs):
            self.assertEqual(kwargs['env']['DOCKER_CONTEXT'], 'desktop-linux')
            self.assertFalse(any('DOCKER_' in arg for arg in args))
            kwargs['stdout'].write(guest_result().encode())
            return Mock(returncode=0, poll=lambda: 0)
        with patch.dict(os.environ, {'DOCKER_CONTEXT': 'desktop-linux', 'DOCKER_HOST': 'operator-endpoint'}), patch.object(sandbox, 'inspect_docker_image', return_value=image_id), patch.object(sandbox, 'cleanup'), patch('backend.agents.sandbox.subprocess.Popen', side_effect=spawn):
            result = sandbox._docker({}, time.monotonic()+10, lambda: None, lambda h: None, 'aura-code-'+'a'*32+'-1')
        self.assertEqual(json.loads(result)['exit_code'], 0)

    def test_inspect_os_errors_retain_safe_windows_error_numbers(self):
        error = PermissionError(13, 'private credentials and path'); error.winerror = 5
        with patch.object(sandbox, '_docker_control', side_effect=error), self.assertRaises(sandbox.SandboxUnavailable) as caught:
            sandbox.inspect_docker_image()
        self.assertEqual(caught.exception.diagnostics, {'stage': 'image_inspect', 'errno': 13, 'winerror': 5})
        self.assertNotIn('private', str(caught.exception)+str(caught.exception.diagnostics))
        with patch.object(sandbox, '_docker_control', return_value=Mock(returncode=1, stdout=b'', stderr=b'private details')), self.assertRaises(sandbox.SandboxUnavailable) as caught:
            sandbox.inspect_docker_image()
        self.assertEqual(caught.exception.diagnostics, {'stage': 'image_inspect', 'exit_code': 1})

    def test_windows_selects_native_exe_instead_of_the_extensionless_docker_shim(self):
        def lookup(name):
            return r'C:\Program Files\Docker\resources\bin\docker.exe' if name == 'docker.exe' else r'C:\Program Files\Docker\resources\bin\docker'
        with patch('backend.agents.sandbox.sys.platform', 'win32'), patch.dict(os.environ, {'AURA_DOCKER_EXECUTABLE': ''}), patch('backend.agents.sandbox.shutil.which', side_effect=lookup) as which:
            self.assertTrue(sandbox.docker_executable().endswith('docker.exe'))
        which.assert_called_once_with('docker.exe')

    def test_windows_never_falls_back_to_a_script_or_shell(self):
        for selected in [None, 'docker', 'docker.cmd', 'docker.bat', 'docker.ps1']:
            with self.subTest(selected=selected), patch('backend.agents.sandbox.sys.platform', 'win32'), patch.dict(os.environ, {'AURA_DOCKER_EXECUTABLE': ''}), patch('backend.agents.sandbox.shutil.which', return_value=selected) as which:
                self.assertIsNone(sandbox.docker_executable())
                which.assert_called_once_with('docker.exe')

    def test_explicit_native_path_and_non_windows_path_lookup(self):
        custom = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
        with patch('backend.agents.sandbox.sys.platform', 'win32'), patch.dict(os.environ, {'AURA_DOCKER_EXECUTABLE': custom}), patch('backend.agents.sandbox.shutil.which', return_value=custom) as which:
            self.assertEqual(sandbox.docker_executable(), custom)
            which.assert_called_once_with(custom)
        with patch('backend.agents.sandbox.sys.platform', 'linux'), patch.dict(os.environ, {'AURA_DOCKER_EXECUTABLE': ''}), patch('backend.agents.sandbox.shutil.which', return_value='/usr/bin/docker') as which:
            self.assertEqual(sandbox.docker_executable(), '/usr/bin/docker')
            which.assert_called_once_with('docker')

    def test_image_checks_run_and_cleanup_share_the_native_executable(self):
        custom = r'C:\Program Files\Docker\resources\bin\docker.exe'
        image = {'Os':'linux', 'Id':'sha256:'+'a'*64, 'Config':{'Env':[]}}
        commands = []
        def control(args, **kwargs):
            commands.append(args)
            return Mock(returncode=0, stdout=json.dumps([image]).encode(), stderr=b'')
        def spawn(args, **kwargs):
            commands.append(args)
            kwargs['stdout'].write(guest_result().encode())
            return Mock(returncode=0, poll=lambda:0)
        # Exercise Windows resolution while transport calls are simulated on Linux.
        with patch.object(sandbox, 'docker_executable', return_value=custom), patch('backend.agents.sandbox.subprocess.run', side_effect=control), patch('backend.agents.sandbox.subprocess.Popen', side_effect=spawn):
            sandbox._docker({}, time.monotonic()+10, lambda:None, lambda h:None, 'aura-code-'+'a'*32+'-1')
        self.assertEqual(len(commands), 3)
        self.assertTrue(all(cmd[0] == custom for cmd in commands))
        self.assertEqual(commands[-1][1:3], ['rm', '-f'])

    def test_reported_winerror_193_has_an_actionable_code(self):
        error = OSError(8, 'private path or command'); error.winerror = 193
        with patch.object(sandbox, '_docker_control', side_effect=error), self.assertRaises(sandbox.SandboxUnavailable) as caught:
            sandbox.inspect_docker_image()
        self.assertEqual(caught.exception.code, 'docker_bad_executable')
        self.assertEqual(caught.exception.diagnostics, {'stage':'image_inspect','errno':8,'winerror':193})
        self.assertNotIn('private', str(caught.exception)+str(caught.exception.diagnostics))


class RuntimeDiagnostic(unittest.TestCase):
    def test_missing_docker_image_survives_runtime_log_and_saved_run(self):
        store = fixtures.FakeStore(req()); store.run['source_id'] = None; model = fixtures.Model([code_action()])
        with patch.object(sandbox, 'backend_name', return_value='docker'), patch.object(store, 'tool', side_effect=sandbox.SandboxUnavailable('docker_image_missing')), self.assertLogs('backend.agents.runtime', level='WARNING') as logs:
            run_agent(store, store.run, lambda: model)
        self.assertEqual(store.run['error_code'], 'docker_image_missing')
        self.assertEqual(store.run['state'], 'failed')
        self.assertIn('failure_code=docker_image_missing', ''.join(logs.output))
        self.assertEqual(len(model.calls), 1)

    def test_unknown_exception_text_is_not_exposed(self):
        store = fixtures.FakeStore(req()); store.run['source_id'] = None; model = fixtures.Model([code_action()])
        with patch.object(sandbox, 'backend_name', return_value='docker'), patch.object(store, 'tool', side_effect=sandbox.SandboxUnavailable('private-error-contents')), self.assertLogs('backend.agents.runtime', level='WARNING') as logs:
            run_agent(store, store.run, lambda: model)
        self.assertEqual(store.run['error_code'], 'runtime_unavailable')
        self.assertNotIn('private-error', str(store.run)+str(logs.output))

    def test_operator_check_is_read_only_by_default_and_smoke_uses_the_isolation_adapter(self):
        from scripts.check_code_runtime import main
        with patch.dict(os.environ, {'AURA_CODE_BACKEND': 'docker'}), patch('scripts.check_code_runtime.load_dotenv'), patch.object(sandbox, 'inspect_docker_image', return_value='sha256:'+'a'*64), patch.object(sandbox, 'execute') as execute:
            self.assertEqual(main([]), 0)
            execute.assert_not_called()
            artifact = {'name': 'result.json', 'data': base64.b64encode(b'{"mean":4}').decode()}
            execute.return_value = {'status': 'succeeded', 'missing_outputs': [], 'artifacts': [artifact]}
            self.assertEqual(main(['--smoke']), 0)
            execute.assert_called_once()
            self.assertIn('assert mean == 4', execute.call_args.args[0])


@unittest.skipUnless(sys.platform == 'linux', 'Guest fixtures use Linux resource limits')
class TrustedGuestFixtures(unittest.TestCase):
    def fixed_fixture(self, source, outputs):
        # Authored literals below only, never model/test-user input. Product never calls this.
        result = subprocess.run([sys.executable, '-I', '-B', 'backend/agents/sandbox_guest.py'],
            input=json.dumps({'code': source, 'files': {'input.csv': 'x\n2\n6\n'}, 'outputs': outputs}),
            capture_output=True, text=True, timeout=20, env={'PATH': '/usr/local/bin:/usr/bin:/bin'})
        self.assertEqual(result.returncode, 0, result.stderr)
        return sandbox.parse_result(result.stdout, source, outputs)

    def test_fixed_csv_fixture_computes_and_returns_actual_file(self):
        source = "import csv, statistics, json\nwith open('input.csv') as f: values=[float(row['x']) for row in csv.DictReader(f)]\nmean=statistics.mean(values)\nprint(mean)\nwith open('result.json','w') as f: json.dump({'mean':mean},f)"
        out = self.fixed_fixture(source, ['result.json'])
        self.assertEqual(out['stdout'].strip(), '4.0')
        self.assertEqual(json.loads(base64.b64decode(out['artifacts'][1]['data'])), {'mean': 4.0})

    def test_fixed_symlink_and_big_stdout_fixtures_are_bounded(self):
        out = self.fixed_fixture("import os\nos.symlink('/etc/passwd','result.txt')\nprint('x'*20000)", ['result.txt'])
        self.assertTrue(out['stdout_truncated'])
        self.assertLessEqual(len(out['stdout'].encode()), 16384)
        self.assertEqual(out['missing_outputs'], ['result.txt'])

    def test_fixed_failure_is_not_success(self):
        out = self.fixed_fixture("raise ValueError('fixed fixture failure')", [])
        self.assertEqual(out['status'], 'failed'); self.assertIn('ValueError', out['stderr'])

    def test_fixed_timeout_fixture_stops_the_process(self):
        out = self.fixed_fixture("import time; time.sleep(60)", [])
        self.assertEqual(out['status'], 'timed_out')


@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'), 'Optional PostgreSQL engine not configured')
class CodePostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.PostgresAgentChecks.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls): cls.bridge.close()
    def setUp(self):
        fixtures.PostgresAgentChecks.setUp(self)
        self.mode = patch.object(sandbox, 'backend_name', return_value='docker'); self.mode.start(); self.addCleanup(self.mode.stop)
    def prepare(self, request=None):
        self.store.create(42, request or req(inputs=[{'name': 'data.csv', 'text': 'x\n4\n'}]))
        return self.store.claim('test-worker')
    def tool(self, run, source='print(4)', outputs=None):
        act = Decision.model_validate(code_action(source, outputs)).action
        return self.store.tool(run, act, {'tool': 'code_execute', 'state': 'completed'})
    def execute(self, sequence, executor, request=None):
        run = self.prepare(request); model = fixtures.Model(sequence)
        with patch.object(sandbox, 'execute', side_effect=executor): run_agent(self.store, run, lambda: model)
        return self.store.runs(42, 3, run['id']), model

    def test_reserved_execution_runs_without_a_database_lock_then_persists(self):
        run = self.prepare()
        def execute(code, outputs, files, **kw):
            self.assertFalse(self.bridge.lock.locked())
            step = self.store.runs(42, 3, run['id'])['steps'][-1]
            self.assertEqual(step['state'], 'running')
            self.assertEqual(files, {'data.csv': 'x\n4\n'})
            kw['check_active'](); kw['on_start']({'backend': 'docker', 'id': 'aura-code-'+'a'*32+'-1'})
            self.assertTrue(self.store.runs(42, 3, run['id'])['steps'][-1]['cleanup_pending'])
            return observed(outputs=outputs)
        with patch.object(sandbox, 'execute', side_effect=execute): self.tool(run, outputs=['result.csv'])
        saved = self.store.runs(42, 3, run['id'])
        self.assertEqual(saved['steps'][-1]['state'], 'completed')
        public = public_run(saved)
        self.assertNotIn('data', public['steps'][-1]['observation']['artifacts'][0])
        self.assertEqual(public['steps'][-1]['action']['code'], 'print(4)')
        self.assertNotIn('execution', public['steps'][-1])
        self.assertNotIn('action_key', public['steps'][-1])

    def test_cancel_and_expiry_discard_late_results(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel):
                fixtures.PostgresAgentChecks.setUp(self); run = self.prepare(req(max_seconds=15))
                def execute(*args, **kwargs):
                    if cancel: self.store.cancel(42, 3, run['id'])
                    else: self.bridge.query('UPDATE aura_agent_runs SET started_at=NOW()-INTERVAL \'20 seconds\'')
                    return observed()
                with patch.object(sandbox, 'execute', side_effect=execute), self.assertRaises(RunStopped): self.tool(run)
                saved = self.store.runs(42, 3, run['id'])
                self.assertEqual(saved['state'], 'cancelled' if cancel else 'timed_out')
                self.assertNotIn('observation', saved['steps'][-1])

    def test_two_attempt_limit_exact_duplicates_and_wrong_skill_are_blocked(self):
        run = self.prepare()
        with patch.object(sandbox, 'execute', return_value=observed()) as execute:
            self.tool(run)
            with self.assertRaises(HTTPException): self.tool(run)
            self.tool(run, 'print(2+2)')
            with self.assertRaises(HTTPException): self.tool(run, 'print(3+1)')
        self.assertEqual(execute.call_count, 2)
        self.store.record(run, state='completed')
        other = self.prepare(RunInput(course_id=3, source_id=7, skill='study_plan', goal='Study'))
        with self.assertRaises(HTTPException): self.tool(other)

    def test_transport_failure_checkpoints_safe_failure_without_replay(self):
        saved, model = self.execute([code_action()], sandbox.SandboxUnavailable('submission_uncertain'))
        self.assertEqual(saved['state'], 'failed')
        self.assertEqual(saved['steps'][-1]['state'], 'failed')
        self.assertEqual(saved['steps'][-1]['error_code'], 'submission_uncertain')
        self.assertEqual(len(model.calls), 1)

    def test_runtime_observes_actual_failure_then_corrects_once(self):
        outputs = iter([observed(1), observed()])
        saved, model = self.execute([code_action('print(bad)'), code_action('print(4)'), fixtures.action(answer='The corrected calculation printed 4.')], lambda *a, **k: next(outputs))
        self.assertEqual(saved['state'], 'completed', saved)
        self.assertFalse(saved['result']['verified'])
        self.assertEqual(saved['result']['code_result']['status'], 'succeeded')
        self.assertEqual(model.calls[1]['prompt']['observations'][0]['data']['status'], 'failed')
        self.assertNotIn('data', model.calls[1]['prompt']['observations'][0]['data']['artifacts'][0])
        self.assertEqual(model.calls[0]['prompt']['execution_context']['inputs'][0]['name'], 'data.csv')
        self.assertEqual(model.calls[1]['prompt']['observations'][0]['executed_program'],'print(bad)')
        attempts=model.calls[2]['prompt']['observations']
        self.assertEqual([row['executed_program'] for row in attempts],['print(bad)','print(4)'])
        self.assertEqual([row['data']['status'] for row in attempts],['failed','succeeded'])
        self.assertTrue(all(row['untrusted_data'] and not row['program_truncated'] for row in attempts))

    def test_explanation_receives_executed_search_checks_and_captured_absent_result(self):
        # Controlled tool/model responses check evidence plumbing, not live model accuracy.
        program="values = [1,3,5,7,9,11,13,15]\nassert 4 not in values\nprint('target=4,index=-1,probes=3')"
        result=sandbox.parse_result(guest_result(stdout='target=4,index=-1,probes=3\n'),program,[])
        saved,model=self.execute([code_action(program),fixtures.action(answer='Target 4 is absent; the observed result was -1 after 3 midpoint probes.')],lambda *a,**k:result)
        self.assertEqual(saved['state'],'completed',saved)
        observation=model.calls[1]['prompt']['observations'][0]
        self.assertEqual(observation['executed_program'],program)
        self.assertEqual(observation['data']['stdout'],'target=4,index=-1,probes=3\n')
        self.assertEqual(len(model.calls),2) # no extra paid judge or automatic code run
        self.assertFalse(saved['result']['verified'])
        self.assertEqual(saved['result']['code_result']['stdout'],result['stdout'])

    def test_display_narration_bounds_cannot_block_valid_code_or_add_an_execution(self):
        for plan in ('x'*181,['  '],['PRIVATE_NARRATION_'*100]):
            with self.subTest(plan_type=type(plan).__name__):
                execute=Mock(return_value=observed())
                code=code_action('print(4)');code['plan']=plan
                finish=fixtures.action(answer='The captured program printed 4.');finish['plan']=plan
                saved,model=self.execute([code,finish],execute)
                self.assertEqual(saved['state'],'completed',saved)
                self.assertEqual(len(model.calls),2);self.assertEqual(execute.call_count,1)
                self.assertFalse(any(step['tool']=='validation' for step in saved['steps']))
                self.assertTrue(all(step['plan']==['Use the selected study tool.'] for step in saved['steps']))
                self.assertEqual(saved['result']['code_result']['stdout'],'4\n')
                self.assertNotIn('PRIVATE_NARRATION',json.dumps(saved))

    def test_long_narration_does_not_allow_invalid_code_arguments(self):
        for bad in ({'tool':'code_execute','title':'Unsafe output','code':'print(4)','outputs':['../bad.csv']},
                    {'tool':'code_execute','title':'Wrong type','code':None,'outputs':[]},
                    {'tool':'code_execute','title':'Extra field','code':'print(4)','outputs':[],'student_id':43}):
            with self.subTest(title=bad['title']):
                raw={'plan':['x'*500],'action':bad};execute=Mock(return_value=observed())
                saved,model=self.execute([raw,raw],execute)
                self.assertEqual(saved['state'],'failed');execute.assert_not_called()
                self.assertEqual(len(model.calls),2)

    def test_failed_code_cannot_be_presented_as_completed(self):
        saved, _ = self.execute([code_action(), fixtures.action(answer='The code failed; no computed result is available.')], lambda *a, **k: observed(1))
        self.assertEqual(saved['state'], 'failed')
        self.assertEqual(saved['error_code'], 'code_execution_failed')

    def test_owned_artifact_download_and_latest_attempt_only(self):
        run = self.prepare()
        with patch.object(sandbox, 'execute', return_value=observed(outputs=['result.csv'])): self.tool(run, outputs=['result.csv'])
        app = FastAPI()
        with patch('backend.agents.routes.Store', return_value=self.store): install_agents(app, lambda: fixtures.Model([]))
        app.dependency_overrides[get_current_student] = lambda: {'student_id': 42}
        with TestClient(app) as client:
            path = f"/agents/runs/{run['id']}/artifacts/result.csv?course_id=3"
            response = client.get(path)
            self.assertEqual(response.status_code, 200); self.assertEqual(response.content, b'value\n4\n')
            self.assertIn('attachment', response.headers['content-disposition'])
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
            self.assertEqual(response.headers['cache-control'], 'private, no-store')
            app.dependency_overrides[get_current_student] = lambda: {'student_id': 43}
            self.assertEqual(client.get(path).status_code, 404)
            app.dependency_overrides[get_current_student] = lambda: {'student_id': 42}
            with patch.object(sandbox, 'execute', return_value=observed(1)): self.tool(run, source='print(bad)')
            self.assertEqual(client.get(path).status_code, 404)
            del app.dependency_overrides[get_current_student]
            self.assertEqual(client.get(path).status_code, 401)

    def test_disabled_backend_and_cross_account_source_cannot_start(self):
        with patch.object(sandbox, 'backend_name', return_value=None), self.assertRaises(HTTPException) as error:
            self.store.create(42, req())
        self.assertEqual(error.exception.status_code, 503)
        with self.assertRaises(HTTPException) as error: self.store.create(43, req(source_id=7))
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.bridge.query('SELECT * FROM aura_agent_runs'), [])

    def test_step_and_token_limits_prevent_execution(self):
        run = self.prepare(req(max_steps=2))
        self.store.record(run, {'tool': 'document_search', 'state': 'completed'})
        self.store.record(run, {'tool': 'document_search', 'state': 'completed'})
        with patch.object(sandbox, 'execute') as execute, self.assertRaises(HTTPException): self.tool(run)
        execute.assert_not_called()
        self.store.record(run, state='completed')
        run = self.prepare(req(max_tokens=4000))
        self.store.record(run, tokens=4000)
        with patch.object(sandbox, 'execute') as execute, self.assertRaises(HTTPException): self.tool(run)
        execute.assert_not_called()

    def test_cleanup_reaper_only_confirms_known_owned_handles(self):
        run = self.prepare(); handle = {'backend': 'docker', 'id': 'aura-code-'+'a'*32+'-1'}
        def execute(*args, **kw):
            kw['on_start'](handle); self.store.cancel(42, 3, run['id']); kw['check_active']()
        with patch.object(sandbox, 'execute', side_effect=execute), self.assertRaises(RunStopped): self.tool(run)
        with patch.object(sandbox, 'cleanup', return_value=True) as cleanup: self.store.cleanup_code()
        cleanup.assert_called_once_with(handle)
        self.assertFalse(self.store.runs(42, 3, run['id'])['steps'][0]['cleanup_pending'])


if __name__ == '__main__': unittest.main()
