"""Trusted guest entrypoint. Executed only inside the configured isolation backend."""
import base64
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import tempfile


def main():
    request = json.loads(sys.stdin.buffer.read(400000))
    with tempfile.TemporaryDirectory(prefix='aura-', dir='/tmp') as directory:
        root = Path(directory)
        for name, text in request['files'].items():
            if Path(name).name != name or name in {'.', '..', 'program.py'}:
                raise ValueError('Invalid input name')
            (root / name).write_text(text, encoding='utf-8')
        (root / 'program.py').write_text(request['code'], encoding='utf-8')
        def limits():
            os.setsid()
            resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
            resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
            resource.setrlimit(resource.RLIMIT_FSIZE, (262144, 262144))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        timed_out = False
        # Regular temporary streams bound output on disk; no pipe can fill and deadlock.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            proc = subprocess.Popen([sys.executable, '-I', '-B', '-u', 'program.py'], cwd=root,
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, preexec_fn=limits,
                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': directory,
                     'LANG': 'C.UTF-8', 'MPLCONFIGDIR': directory})
            try:
                proc.wait(timeout=12)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=2)
            def output(stream):
                stream.seek(0)
                raw = stream.read(16385)
                return raw[:16384].decode('utf-8', errors='replace'), len(raw) > 16384
            out, out_cut = output(stdout)
            err, err_cut = output(stderr)
        artifacts, total = [], 0
        if proc.returncode == 0 and not timed_out:
            for name in request['outputs']:
                if Path(name).name != name:
                    continue
                try:
                    fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, 'rb') as file:
                        metadata = os.fstat(file.fileno())
                        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 131072:
                            continue
                        raw = file.read(131073)
                        if len(raw) > 131072 or total + len(raw) > 196608:
                            continue
                    artifacts.append({'name': name, 'data': base64.b64encode(raw).decode('ascii')})
                    total += len(raw)
                except OSError:
                    continue
        print(json.dumps({'exit_code': proc.returncode, 'timed_out': timed_out,
            'stdout': out, 'stderr': err, 'stdout_truncated': out_cut, 'stderr_truncated': err_cut,
            'artifacts': artifacts}, ensure_ascii=True))


if __name__ == '__main__':
    main()
