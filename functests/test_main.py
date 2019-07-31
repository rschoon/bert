
import io
import os
import tempfile

# XXX We're using an internal interface so we can
# provide our source from eval
import pytest
from _pytest._code import compile as pytest_compile

from bert.display import Display
from bert.build import BertBuild
from bert.yaml import from_yaml

class ConfigAssert(object):
    def __init__(self, info):
        if isinstance(info, str):
            self.code = info
        else:
            self.code = info.pop("code")
        if self.code is None:
            raise TypeError("Invalid type for code")

class Config(object):
    def __init__(self, test_id, filename, data):
        self.test_id = test_id
        self.filename = filename
        self.data = data

    def __str__(self):
        return "<Config({0.filename})>".format(self)

    @property
    def asserts(self):
        asserts = self.data['asserts']
        if isinstance(asserts, list):
            return [ConfigAssert(a) for a in asserts]
        return [ConfigAssert(asserts)]

    @property
    def files(self):
        return self.data.get("files", ())

    @property
    def root_dir(self):
        return os.path.dirname(self.filename)

    @property
    def temp_dir(self):
        return self.data.get("temp-dir", False)

    @property
    def root(self):
        return os.path.dirname(self.filename)

    @property
    def config(self):
        return self.data["src"]

def _get_test_id(t):
    return t.test_id

def find_tests():
    root = os.path.dirname(__file__)
    for path, dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".yml") and f[0] not in ("_", "."):
                fn = os.path.join(path, f)
                with open(fn) as fo:
                    yield Config(fn[len(root)+1:], fn, from_yaml(fo))

@pytest.mark.skipif("BERT_FUNCTESTS" not in os.environ, reason="To run functional tests, set BERT_FUNCTESTS envvar")
@pytest.mark.parametrize("tconfig", find_tests(), ids=_get_test_id)
def test_config(tconfig):
    display = Display(interactive=False, stdin=io.StringIO())
    td = None
    vars = {}

    try:
        if tconfig.temp_dir or tconfig.files:
            td = tempfile.TemporaryDirectory()
            vars['functest_temp_dir'] = td.name

        if tconfig.files:
            for fin, fic in tconfig.files.items():
                with open(os.path.join(td.name, fin), "w") as f:
                    f.write(fic)

        b = BertBuild(None, config=tconfig.config, display=display, root_dir=tconfig.root_dir)
        result = b.build(vars=vars)

        for a in tconfig.asserts:
            env = {
                'assert_info' : a,
                'b' : b,
                'tconfig' : tconfig,
                'result' : result
            }
            env.update(vars)

            code = pytest_compile(a.code, '<string>', 'exec')
            try:
                exec(code, globals(), env)
            except Exception:
                print("Vars: {}".format(result.vars))
                raise
    finally:
        if td is not None:
            td.cleanup()