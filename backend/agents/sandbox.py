"""Bounded Python execution in Token Factory VMs or explicitly enabled Docker.

There is deliberately no host-Python execution path and no automatic backend
failover after a possibly accepted paid submission. Results remain untrusted.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from uuid import UUID

import requests

BASE = 'https://api.tokenfactory.nebius.com/sandboxes/v1'
MAX_RESPONSE = 524288
MAX_HTTP_RESPONSE = 2097152  # Operation metadata can include both input and encoded output.
MAX_ARTIFACT = 131072
MAX_ARTIFACT_TOTAL = 196608
MAX_EXECUTIONS = 2
GUEST = Path(__file__).with_name('sandbox_guest.py').read_text(encoding='utf-8')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,74}\.(csv|json|txt|md|png)\Z')
MIME = {'csv': 'text/csv', 'json': 'application/json', 'txt': 'text/plain', 'md': 'text/markdown', 'png': 'image/png', 'py': 'text/plain'}


class SandboxUnavailable(Exception):
    def __init__(self, code):
        allowed = {'not_configured', 'runtime_unavailable', 'submission_uncertain', 'invalid_result', 'execution_timeout'}
        self.code = code if code in allowed else 'runtime_unavailable'
        super().__init__(self.code)


def backend_name():
    mode = os.getenv('AURA_CODE_BACKEND', 'disabled').strip().lower()
    if mode == 'nebius':
        try:
            UUID(os.getenv('NEBIUS_SANDBOX_IMAGE', ''))
        except ValueError:
            return None
        key = os.getenv('NEBIUS_API_KEY', '').strip()
        project = os.getenv('NEBIUS_PROJECT_ID', '').strip()
        return 'nebius' if key and not key.startswith('replace_') and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', project) else None
    if mode == 'docker':
        image = os.getenv('AURA_DOCKER_IMAGE', 'aura-code:1')
        return 'docker' if shutil.which('docker') and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/@:-]{0,200}', image) else None
    return None


def _artifact(name, raw):
    kind = name.rsplit('.', 1)[-1]
    if kind == 'png' and (not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) < 24):
        raise SandboxUnavailable('invalid_result')
    return {'name': name, 'mime': MIME[kind], 'size': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'data': base64.b64encode(raw).decode('ascii')}


def parse_result(raw, code, outputs):
    try:
        value = json.loads(raw)
        if (not isinstance(value, dict) or type(value.get('exit_code')) is not int
                or type(value.get('timed_out')) is not bool
                or any(not isinstance(value.get(k), str) or len(value[k].encode('utf-8')) > 65536 for k in ('stdout', 'stderr'))
                or any(type(value.get(k)) is not bool for k in ('stdout_truncated', 'stderr_truncated'))
                or not isinstance(value.get('artifacts'), list) or len(value['artifacts']) > 4):
            raise ValueError()
        artifacts, seen, total = [], set(), 0
        for item in value['artifacts']:
            name = item['name']
            if name not in outputs or name in seen or not NAME.fullmatch(name):
                raise ValueError()
            data = base64.b64decode(item['data'], validate=True)
            total += len(data)
            if len(data) > MAX_ARTIFACT or total > MAX_ARTIFACT_TOTAL:
                raise ValueError()
            seen.add(name)
            artifacts.append(_artifact(name, data))
        success = value['exit_code'] == 0 and not value['timed_out']
        if not success:
            artifacts = []; seen = set()
        artifacts.insert(0, _artifact('program.py', code.encode('utf-8')))
        return {'status': 'succeeded' if success else 'timed_out' if value['timed_out'] else 'failed',
                **{k: value[k] for k in ('exit_code', 'stdout', 'stderr', 'stdout_truncated', 'stderr_truncated')},
                'artifacts': artifacts, 'missing_outputs': [name for name in outputs if name not in seen],
                'untrusted_data': True}
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        raise SandboxUnavailable('invalid_result') from error


def _headers():
    return {'Authorization': 'Bearer ' + os.environ['NEBIUS_API_KEY'].strip(),
            'Project': os.environ['NEBIUS_PROJECT_ID'].strip(), 'Content-Type': 'application/json'}


def _http(method, path, deadline, **kwargs):
    remaining = deadline - time.monotonic()
    if remaining <= .1:
        raise SandboxUnavailable('execution_timeout')
    try:
        with requests.request(method, BASE + path, headers=_headers(), allow_redirects=False,
                              stream=True, timeout=(min(3, remaining/3), min(8, remaining*2/3)), **kwargs) as reply:
            if not 200 <= reply.status_code < 300:
                raise SandboxUnavailable('runtime_unavailable')
            body = bytearray()
            # Check wall time even if the peer dribbles bytes without triggering
            # a socket read timeout. Large buffered chunks can hide that case.
            for chunk in reply.iter_content(1):
                body.extend(chunk)
                if len(body) > MAX_HTTP_RESPONSE or time.monotonic() > deadline:
                    raise SandboxUnavailable('invalid_result')
            return json.loads(body) if body else {}
    except (requests.RequestException, ValueError, KeyError) as error:
        raise SandboxUnavailable('runtime_unavailable') from error


def _stream_text(stream):
    if (not isinstance(stream, dict) or stream.get('truncated') is not False
            or not isinstance(stream.get('value'), str)):
        raise SandboxUnavailable('invalid_result')
    try:
        if stream.get('encoding') == 'base64':
            return base64.b64decode(stream['value'], validate=True).decode('utf-8')
        if stream.get('encoding') in ('ascii', 'utf-8'):
            return stream['value']
    except (ValueError, UnicodeError) as error:
        raise SandboxUnavailable('invalid_result') from error
    raise SandboxUnavailable('invalid_result')


def _nebius(request, deadline, check_active, on_start):
    handle = None
    terminal = False
    try:
        check_active()
        payload = {'image': os.environ['NEBIUS_SANDBOX_IMAGE'],
            'command': '/usr/local/bin/python', 'args': ['-I', '-B', '-u', '-c', GUEST],
            'shell': False, 'disposable': True, 'preserve_env': False,
            'uid': 65534, 'gid': 65534, 'cwd': '/tmp',
            'env': {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', 'LANG': 'C.UTF-8'},
            'networking': {'enabled': False}, 'resources_limits': {'max_layer_bytes': 33554432},
            'timeout': 20, 'truncate_output_at': MAX_RESPONSE,
            'stdin': {'value': base64.b64encode(json.dumps(request).encode()).decode(), 'encoding': 'base64', 'close': True}}
        try:
            submitted = _http('POST', '/instances', deadline, json=payload)
        except SandboxUnavailable as error:
            # Never repeat an uncertain submission, nor switch backends automatically.
            raise SandboxUnavailable('submission_uncertain') from error
        handle = {'backend': 'nebius', 'id': str(UUID(submitted['uuid']))}
        on_start(handle)
        while True:
            check_active()
            state = _http('GET', '/operations/' + handle['id'], deadline)
            if state.get('uuid') != handle['id']:
                raise SandboxUnavailable('invalid_result')
            if state.get('status') in ('SUCCESS', 'FAILED', 'CANCELLED'):
                terminal = True
                if state['status'] != 'SUCCESS':
                    raise SandboxUnavailable('runtime_unavailable')
                result = state.get('metadata', {}).get('result', {})
                process = result.get('state', {})
                if type(process.get('exit_code')) is not int or process['exit_code'] != 0 or process.get('signal') or process.get('timed_out'):
                    raise SandboxUnavailable('runtime_unavailable')
                return _stream_text(result.get('stdout'))
            if state.get('status') not in ('PENDING', 'ASSIGNED', 'EXECUTING'):
                raise SandboxUnavailable('invalid_result')
            if time.monotonic() >= deadline:
                raise SandboxUnavailable('execution_timeout')
            time.sleep(.5)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise SandboxUnavailable('invalid_result') from error
    finally:
        if handle and not terminal:
            cleanup(handle)


def _docker_env():
    # Docker's client may need its normal Desktop context; none of this is passed to the guest.
    return {key: value for key, value in os.environ.items()
            if key in {'PATH', 'SYSTEMROOT', 'WINDIR', 'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'}}


def _docker_control(args, timeout=5):
    return subprocess.run([shutil.which('docker') or 'docker', *args], stdin=subprocess.DEVNULL,
                          capture_output=True, timeout=timeout, env=_docker_env(), check=False)


def _docker(request, deadline, check_active, on_start, name):
    handle = {'backend': 'docker', 'id': name}
    proc = None
    on_start(handle)  # Store the owned name before starting the container.
    try:
        check_active()
        inspected = _docker_control(['image', 'inspect', os.getenv('AURA_DOCKER_IMAGE', 'aura-code:1')])
        images = json.loads(inspected.stdout)
        if inspected.returncode or not isinstance(images, list) or len(images) != 1:
            raise SandboxUnavailable('runtime_unavailable')
        image = images[0]
        allowed_env = {'PATH','LANG','LC_ALL','HOME','TZ','PYTHON_VERSION','PYTHON_SHA256','GPG_KEY','PYTHONUNBUFFERED'}
        if (image.get('Os') != 'linux' or not re.fullmatch(r'sha256:[a-f0-9]{64}', image.get('Id', ''))
                or image.get('Config', {}).get('Volumes')
                or any(value.split('=', 1)[0] not in allowed_env for value in image.get('Config', {}).get('Env', []))):
            raise SandboxUnavailable('runtime_unavailable')
        check_active()
        args = [shutil.which('docker') or 'docker', 'run', '--rm', '--pull=never', '--name', name,
            '--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
            '--memory=320m', '--memory-swap=320m', '--cpus=1', '--pids-limit=64', '--user=65534:65534',
            '--tmpfs=/tmp:rw,noexec,nosuid,size=32m,mode=1777', '--workdir=/tmp',
            '--env=HOME=/tmp', '--env=LANG=C.UTF-8', '--entrypoint=/usr/local/bin/python', '-i',
            image['Id'], '-I', '-B', '-u', '-c', GUEST]
        # Host streams are regular files and are capped by the monitoring loop.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as source:
            source.write(json.dumps(request).encode()); source.seek(0)
            proc = subprocess.Popen(args, stdin=source, stdout=out, stderr=err, env=_docker_env())
            while proc.poll() is None:
                check_active()
                if time.monotonic() >= deadline:
                    raise SandboxUnavailable('execution_timeout')
                if os.fstat(out.fileno()).st_size > MAX_RESPONSE or os.fstat(err.fileno()).st_size > MAX_RESPONSE:
                    raise SandboxUnavailable('invalid_result')
                time.sleep(.2)
            if proc.returncode:
                raise SandboxUnavailable('runtime_unavailable')
            out.seek(0); raw = out.read(MAX_RESPONSE+1)
            if len(raw) > MAX_RESPONSE:
                raise SandboxUnavailable('invalid_result')
            return raw.decode('utf-8')
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        raise SandboxUnavailable('runtime_unavailable') from error
    finally:
        cleanup(handle)
        if proc and proc.poll() is None:
            proc.kill(); proc.wait(timeout=3)


def cleanup(handle):
    """Idempotent, best-effort cleanup; accepts only server-generated handles."""
    try:
        if handle.get('backend') == 'nebius':
            identity = str(UUID(handle['id']))
            state = _http('GET', '/operations/' + identity, time.monotonic()+5)
            if state.get('status') in ('SUCCESS', 'FAILED', 'CANCELLED'):
                return True
            _http('DELETE', '/operations/' + identity, time.monotonic()+5)
            return False  # Accepted cancellation is not a confirmed terminal state.
        if handle.get('backend') == 'docker' and re.fullmatch(r'aura-code-[a-f0-9]{32}-[0-9]+', handle.get('id', '')):
            reply = _docker_control(['rm', '-f', handle['id']])
            return reply.returncode == 0 or b'No such container' in reply.stderr
    except (SandboxUnavailable, ValueError, KeyError, OSError, subprocess.SubprocessError, TypeError):
        pass
    return False


def execute(code, outputs, files, *, run_id, attempt, seconds, check_active, on_start):
    mode = backend_name()
    if not mode:
        raise SandboxUnavailable('not_configured')
    deadline = time.monotonic() + max(.2, min(30, seconds))
    request = {'code': code, 'outputs': outputs, 'files': files}
    raw = (_nebius(request, deadline, check_active, on_start) if mode == 'nebius' else
           _docker(request, deadline, check_active, on_start, f'aura-code-{UUID(str(run_id)).hex}-{attempt}'))
    result = parse_result(raw, code, outputs)
    result['backend'] = mode
    return result


def public_output(observation):
    return {**observation, 'artifacts': [{key: value for key, value in item.items() if key != 'data'}
                                      for item in observation.get('artifacts', [])]}


def code_result(action, observations):
    outputs = [item['data'] for item in observations if item['tool'] == 'code_execute']
    if not outputs:
        raise SandboxUnavailable('invalid_result')
    output = outputs[-1]
    return {'text': action.answer, 'references': action.references, 'verified': False,
            'provenance': 'executed_code_draft', 'code_result': public_output(output)}
