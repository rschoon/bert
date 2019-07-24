
import click
import io
import struct
import sys

import dockerpty

def _pump_streams(docker_out, stdout, stderr):
    while True:
        header = docker_out.read(8)
        if not header:
            break
        stype, length = struct.unpack('>BxxxL', header)

        buffer = []
        while length > 0:
            chunk = docker_out.read(length)
            if not chunk:
                break
            length -= len(chunk)
            buffer.append(chunk)

        line = b"".join(buffer)
        if stype == 1:
            stdout.buffer.write(line)
        elif stype == 2:
            stderr.buffer.write(line)

class _WriteCapture(io.BufferedIOBase):
    def __init__(self, inner, buf):
        self._inner = inner
        self._buf = buf

    def write(self, b):
        self._inner.write(b)
        self._buf.write(b)

class WatchResult(object):
    def __init__(self, stdout=None):
        self.stdout = stdout

class Display(object):
    def __init__(self, interactive=True, stdin=None, stdout=None, stderr=None):
        self.interactive = interactive
        self.stdout = stdout if stdout is not None else sys.stdout
        self.stderr = stderr if stderr is not None else sys.stderr
        self.stdin = stdin if stdin is not None else sys.stdin

    def watch_container(self, docker_client, container, capture=False):
        stdin = self.stdin
        stdout = self.stdout
        stderr = self.stderr

        cap_out = None
        if capture:
            cap_out = io.BytesIO()
            buffer = _WriteCapture(stdout.buffer, cap_out)
            stdout = io.TextIOWrapper(buffer)

        if self.interactive:
            dockerpty.start(
                docker_client.api, container.id,
                stdout=stdout,
                stderr=stderr,
                stdin=stdin,
                interactive=self.interactive,
                logs=1
            )
        else:
            docker_out = docker_client.api.attach_socket(container.id, {
                'stdout': 1, 'stderr': 1, 'stream': 1
            })
            docker_client.api.start(container.id)

            _pump_streams(docker_out, stdout, stderr)

        return WatchResult(stdout=None if cap_out is None else cap_out.getvalue())

    def echo(self, *args, **kwargs):
        err = kwargs.get("err", False)
        click.echo(*args, file=self.stderr if err else self.stdout, **kwargs)
