
import collections
from enum import Enum
import fnmatch
import pathlib
import posixpath
import re
import tarfile

from .. import utils

REGEX_SAFE_BACKSLASH = {
    '[': '[', '\\': '\\', '/': '/', ']': ']', '(': '(', ')': ')',
    '.': '.', '*': '*', '?': '?', 'n': '\n', 'a': '\a',
    'r': '\r', 'b': '\b', 'f': '\f', 't': '\t', 'v': '\v'
}

class Prefix(object):
    def __init__(self, path, extra=""):
        self.path = path
        self.extra = extra

    def __eq__(self, other):
        if isinstance(other, str):
            return self.path == other and not self.extra
        return (self.path, self.extra) == (other.path, other.extra)

    def __hash__(self):
        return hash((self.path, self.extra))

    def __repr__(self):
        return "Prefix(%r, %r)" % (self.path, self.extra)

class _Segments(object):
    def __init__(self, value):
        self.value = value
        self.items = []
        self.skip_i = 0
        self.end_i = None

    def __repr__(self):
        return "<_Segments({0.value!r}, {0.items!r}, {0.skip_i!r}, {0.end_i!r})>".format(self)

    def use_until(self, marker):
        # absolute
        self.items.append(self.value[self.skip_i:marker])
        self.skip_i = marker

    def replace(self, s, clen):
        # relative
        self.items.append(s)
        self.skip_i += clen

    def end_at(self, marker):
        self.end_i = marker

    def finish(self):
        prefix = None
        is_full = False
        if self.items:
            end_i = self.end_i if self.end_i is not None else len(self.value)
            self.items.append(self.value[self.skip_i:end_i])
            prefix = "".join(self.items)
            is_full = self.end_i == len(self.value)
        elif self.end_i is None:
            prefix = self.value
        else:
            prefix = self.value[0:self.end_i]
            is_full = self.end_i == len(self.value)

        return prefix, is_full

def _regex_prefix(value):
    slash_i = None
    u_width = None
    segments = _Segments(value)
    is_slash = False
    full_end = False
    for i, c in enumerate(value):
        if u_width is not None:
            u_width -= 1
            if u_width == 0:
                u_width = None
                segments.use_until(slash_i)
                segments.replace(chr(int(value[slash_i+2:i+1], 16)), i-slash_i+1)
                continue
        if is_slash:
            is_slash = False
            if c == 'u':
                u_width = 4
            elif c == 'U':
                u_width = 8
            else:
                cesc = REGEX_SAFE_BACKSLASH.get(c)
                if cesc is not None:
                    segments.use_until(slash_i)
                    segments.replace(cesc, 2)
                else:
                    segments.end_at(i-1)
                    break
            continue

        if c in ("[", ".", "*", "+", "{", "|", "("):
            segments.end_at(i)
            break
        elif c == '$':
            segments.end_at(i)
            full_end = True
            break
        elif c == '\\':
            is_slash = True
            slash_i = i

    prefix, is_full = segments.finish()
    if is_full or full_end:
        return Prefix(prefix)
    else:
        return Prefix(posixpath.dirname(prefix), posixpath.basename(prefix))

class _TargetTree(object):
    __slots__ = ('items', 'leaf')

    def __init__(self, paths=()):
        self.leaf = False
        self.items = collections.defaultdict(self.__class__)
        for path in paths:
            self.insert(path)

    def insert(self, path):
        i = path.find('/', 1)
        if i < 0:
            # make as leaf
            self.items[path].leaf = True
        else:
            # make and descend
            self.items[path[:i]].insert(path[i:])

    def __bool__(self):
        return len(self.items) > 0

    def __iter__(self):
        for path, tree in self.items.items():
            if not tree or tree.leaf:
                yield path
            else:
                for subpath in tree:
                    yield path + subpath

#
#
#

class TarGlobList(object):
    def __init__(self, items=None):
        if items is not None:
            if isinstance(items, str):
                self._items = [TarGlob(items)]
            else:
                self._items = [TarGlob(i) for i in items]
        else:
            self._items = []

    def __iter__(self):
        return iter(self._items)

    def iter_targets(self):
        yield from _TargetTree(item.static_prefix.path for item in self)

    def matches(self, path):
        path = pathlib.PurePosixPath(path)
        while len(path.parts) > 1:
            for item in self:
                if item.matches(str(path)):
                    return True
            path = pathlib.PurePosixPath(*path.parts[:-1])
        return False

    def iter_container_files(self, container):
        for target in self.iter_targets():
            if target.endswith("/"):
                target_prefix = target
            else:
                target_prefix = posixpath.dirname(target)

            tstream, tstat = container.get_archive(target)
            tf = utils.IOFromIterable(tstream)

            with tarfile.open(fileobj=tf, mode="r|") as tin:
                while True:
                    ti = tin.next()
                    if ti is None:
                        break

                    ti.name = posixpath.join(target_prefix, ti.name)
                    if self.matches(ti.name):
                        yield ti, tin.extractfile(ti) if ti.isreg() else None

    def __len__(self):
        return len(self._items)

class TarGlob(object):
    class Type(Enum):
        LITERAL = 1
        GLOB = 2
        REGEX = 3

    DICT_TYPES = {
        "value": Type.LITERAL,
        "literal": Type.LITERAL,
        "glob": Type.GLOB,
        "regex": Type.REGEX
    }

    def __init__(self, item):
        self.type = self.Type.LITERAL
        self.value = None
        self._regex_pattern = None
        self._regex = None

        if isinstance(item, str):
            if item.startswith("glob:"):
                self.type = self.Type.GLOB
                self.value = item[5:]
            elif item.startswith("regex:"):
                self.type = self.Type.REGEX
                self.value = item[6:]
                if not self.value.startswith("^"):
                    self.value = "^"+self.value
            else:
                self.value = item
        elif isinstance(item, dict):
            item = dict(item)
            for tfield, tval in self.DICT_TYPES.items():
                value = item.pop(tfield, None)
                if value is not None:
                    if self.value is not None:
                        raise ValueError("Already have value from %s" % self.type)
                    else:
                        self.value = value
                        self.type = tval

            if self.value is None:
                raise ValueError("Need value")
        else:
            raise TypeError("Expected str or dict")

        if self.type == self.Type.REGEX:
            self._regex_pattern = self.value
        elif self.type == self.Type.GLOB:
            self._regex_pattern = "^" + fnmatch.translate(self.value)
        if self._regex_pattern is not None:
            self._regex = re.compile(self._regex_pattern)

    RE_UNWRAP_DOTALL = re.compile(r'^\^\(\?s:(.*?)\)(\\Z|\$)$')

    def matches(self, path):
        if self._regex is not None:
            return self._regex.search(path)
        return self.value == path

    @property
    def static_prefix(self):
        """Return a static prefix for an item"""
        if self._regex_pattern is not None:
            if not self._regex_pattern or self._regex_pattern[0] != "^":
                return Prefix("")

            m = self.RE_UNWRAP_DOTALL.search(self._regex_pattern)
            if m is not None:
                pattern = m.group(1)
            else:
                pattern = self._regex_pattern[1:]

            return _regex_prefix(pattern)
        return Prefix(self.value)
