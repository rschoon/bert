
import os
import pytest
import tempfile

PATCH_DATA = os.path.join(os.path.dirname(__file__), "patch-data")

def make_layout(root, input):
    import shutil

    for dest, src in input.items():
        fn = os.path.join(root, dest)
        with open(fn, "wb") as f:
            with open(os.path.join(PATCH_DATA, src), "rb") as f2:
                shutil.copyfileobj(f2, f)

def export_layout(root):
    data = {}
    for here, dirs, files in os.walk(root):
        for fn in files:
            pth = os.path.join(here, fn)
            with open(pth, "rb") as f:
                pth2 = pth[len(root):]
                while pth2.startswith("/"):
                    pth2 = pth2[1:]
                data[pth2] = f.read()
    return data

def assert_layout(layout, expected):
    for fn, src in expected.items():
        with open(os.path.join(PATCH_DATA, src), "rb") as f:
            assert layout[fn].split(b"\n") == f.read().split(b"\n")

def run_patcher(tempdir, input, patch, flags):
    from bert.tasks.patch import Patch

    make_layout(tempdir.name, input)

    with open(os.path.join(PATCH_DATA, patch), "r") as f:
        kwargs = {}
        if 'strip_dir' in flags:
            kwargs['strip_dir'] = flags['strip_dir']
        p = Patch(f.read(), **kwargs)
    p.apply(tempdir.name)
    
    return export_layout(tempdir.name)

#
#
#

@pytest.mark.parametrize('input,patch,output,flags', [
    (
        {'hello.txt' : 'hello-in-1.txt'},
        "hello-1-context.diff",
        {'hello.txt' : 'hello-out-1.txt'},
        {'strip_dir' : 1}
    ),
    (
        {'hello.txt' : 'hello-in-1.txt'},
        "hello-1-unified.diff",
        {'hello.txt' : 'hello-out-1.txt'},
        {'strip_dir' : 1}
    ),
    (
        {'hello.txt' : 'hello-in-1.txt'},
        "hello-1-nostrip.diff",
        {'hello.txt' : 'hello-out-1.txt'},
        {}
    ),
    (
        {'hello.txt' : 'hello-in-2.txt'},
        "hello-1-context.diff",
        {'hello.txt' : 'hello-out-2.txt'},
        {'strip_dir' : 1}
    ),
    (
        {'hello.txt' : 'hello-in-3.txt'},
        "hello-1-context.diff",
        {'hello.txt' : 'hello-out-3.txt'},
        {'strip_dir' : 1}
    ),
])
def test_patcher(input, patch, output, flags):
    tempdir = tempfile.TemporaryDirectory()
    try:
        assert_layout(run_patcher(tempdir, input, patch, flags), output)
    finally:
        tempdir.cleanup()

#
#
#

@pytest.mark.parametrize('input,patch,exc,flags', [
    (
        # Should fail because strip_dir is not provided
        {'hello.txt' : 'hello-in-1.txt'},
        "hello-1-unified.diff",
        lambda pe: pytest.raises(pe, match=r'does not exist'),
        {}
    )
])
def test_patcher_fails(input, patch, exc, flags):
    from bert.tasks.patch import PatchError

    tempdir = tempfile.TemporaryDirectory()
    try:
        with exc(PatchError):
            run_patcher(tempdir, input, patch, flags)
    finally:
        tempdir.cleanup()