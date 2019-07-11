

import unittest

class TestPrefix(unittest.TestCase):
    def setUp(self):
        from bert.utils.targlob import TarGlob, Prefix
        self.TarGlob = TarGlob
        self.Prefix = Prefix

    def static_prefix(self, s):
        return self.TarGlob(s).static_prefix

    def test_literal(self):
        assert self.static_prefix(r"/abcd/ef") == "/abcd/ef"

    def test_regex(self):
        assert self.static_prefix(r"regex:/abcd") == self.Prefix('/', 'abcd')
        assert self.static_prefix(r"regex:/abcd/") == '/abcd'
        assert self.static_prefix(r"regex:/abc[q4]/") == self.Prefix('/', 'abc')
        assert self.static_prefix(r"regex:/abc\u4e10/") == "/abc\u4e10"
        assert self.static_prefix(r"regex:/abc\u4e10ef/") == "/abc\u4e10ef"
        assert self.static_prefix(r"regex:/abc\u4e10ef\d/") == self.Prefix("/", "abc\u4e10ef")
        assert self.static_prefix(r"regex:/abc\u4e10ef\[/") == self.Prefix("/abc\u4e10ef[")
        assert self.static_prefix(r"regex:/\dabc/") == self.Prefix("/", "")
        assert self.static_prefix(r"regex:/abc\def/") == self.Prefix("/", "abc")
        assert self.static_prefix(r"regex:/abc\nk/") == self.Prefix("/abc\nk")
        assert self.static_prefix(r"regex:/abc\nk/def") == self.Prefix("/abc\nk", "def")
        assert self.static_prefix(r"regex:/abc\nk/def$") == self.Prefix("/abc\nk/def")

    def test_glob(self):
        assert self.static_prefix(r"glob:/abc/*/def") == self.Prefix("/abc")
        assert self.static_prefix(r"glob:/abc*") == self.Prefix("/", "abc")

class TestList(unittest.TestCase):
    def setUp(self):
        from bert.utils.targlob import  TarGlobList
        self.TarGlobList = TarGlobList

    def targlob_targets(self, *args, **kwargs):
        return set(map(str, self.TarGlobList(*args, **kwargs).iter_targets()))

    def test_empty(self):
        assert len(self.TarGlobList()) == 0

    def test_targets(self):
        assert self.targlob_targets(["regex:/abc/def", "/abc/ghb"]) \
            == {"/abc"}
        assert self.targlob_targets(["regex:/abc/def", "/bin/ghb"]) \
            == {"/abc", "/bin/ghb"}
