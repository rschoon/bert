
import hashlib
import io
import json
import os
import re
import struct

def decode_bin(s, encoding=None):
    if encoding is None:
        encoding = "utf-8"
    if encoding in ("bin", "binary", "bytes", "raw"):
        return s
    return s.decode(encoding)

class open_output(object):
    def __init__(self, filename, mode="wb"):
        self._dirname = os.path.dirname(filename)
        self.filename = str(filename)
        self._tmpname = self.filename+".tmp"
        self.mode = mode
        self._fileobj = None

    def __enter__(self):
        if self._dirname:
            os.makedirs(self._dirname, exist_ok=True)
        self._fileobj = open(self._tmpname, self.mode)
        return self._fileobj

    def __exit__(self, type, value, tb):
        self.close(value is None)

    def close(self, commit=True):
        if self._fileobj is not None:
            self._fileobj.close()
            if commit:
                os.rename(self._tmpname, self.filename)
            else:
                os.unlink(self._tmpname)
            self._fileobj = None

def expect_file_mode(mode, _sub_mode_re=re.compile('^(u|g|o)=([rwx]+)$')):
    if mode is None or mode == "":
        return None

    if isinstance(mode, int):
        return mode

    modes = mode.split(",")
    rv = 0
    for sm in modes:
        m = _sub_mode_re.match(sm)
        if not m:
            raise ValueError('Invalud mode value %s in %s' % (sm, mode))
        shift = ("o", "g", "u").index(m.group(1))*3
        bits = 0
        for bi in m.group(2):
            bits |= 2**('x', 'w', 'r').index(bi)
        rv |= (bits << shift)
    return rv

def json_hash(name, value):
    h = hashlib.new(name)
    h.update(json.dumps(value, sort_keys=True).encode('utf-8'))
    return h.hexdigest()

def _file_hash(name, filename, chunk_size=2**16):
    h = hashlib.new(name)
    sz = 0

    with open(filename, "rb") as f:
        while True:
            chunk = f.read()
            if not chunk:
                break

            sz += len(chunk)
            h.update(chunk)

    return h, sz

def file_hash(name, filename):
    filename = os.fspath(filename)
    if os.path.isfile(filename):
        h, _ = _file_hash(name, filename)
        return h.hexdigest()

    h = hashlib.new(name)
    dirs = [filename]

    while dirs:
        dirs = sorted(dirs)
        dirname = dirs.pop()

        for n in os.listdir(dirname):
            fn = os.path.join(dirname, n)
            if os.path.isdir(fn):
                dirs.append(fn)
            else:
                fn_u8 = fn.encode('utf-8')

                h.update(struct.pack('L', len(fn_u8)))
                h.update(fn_u8)

                hf, sf = _file_hash(name, fn)

                h.update(struct.pack('Q', sf))
                h.update(hf.digest())
    return h.hexdigest()

def value_hash(name, value):
    h = hashlib.new(name)
    if isinstance(value, str):
        value = value.encode('utf-8')
    h.update(value)
    return h.hexdigest()

class IOHashWriter(io.IOBase):
    def __init__(self, hash_name, fileobj):
        if not fileobj.writable():
            raise ValueError("IOHashWriter requires writable fileobj")
        self._h = hashlib.new(hash_name)
        self._inner = fileobj

    def digest(self):
        return self._h.digest()

    def hexdigest(self):
        return self._h.hexdigest()

    @property
    def closed(self):
        return self._inner.closed

    def close(self):
        pass

    def fileno(self):
        return self._inner.fileno()

    def seek(self):
        raise OSError("Not seekable")

    def seekable(self):
        return False

    def tell(self):
        return self._inner.tell()

    def readable(self):
        return False

    def truncate(self, size=None):
        raise OSError("Not truncatable")

    def writable(self):
        return self._inner.writable()

    def write(self, b):
        self._h.update(b)
        return self._inner.write(b)

class IOFromIterable(io.RawIOBase):
    def __init__(self, iterable):
        self._iter = iter(iterable)
        self._pos = 0

    def readinto(self, buf):
        try:
            chunk = next(self._iter)
        except StopIteration:
            return 0

        sz = len(chunk)
        buf[:sz] = chunk
        self._pos += sz
        return sz

    def tell(self):
        return self._pos
