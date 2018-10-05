
import ast
import hashlib
import io
import json
import os
import re
import struct

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
            raise ValueError('Invalud mode value %s in %s'%(sm, mode))
        shift = ("o","g","u").index(m.group(1))*3
        bits = 0
        for bi in m.group(2):
            bits |= 2**('x','w','r').index(bi)
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
