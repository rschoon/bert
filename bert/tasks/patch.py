
import os
import posixpath
import shutil
import tarfile
import tempfile

import whatthepatch

from . import Task
from ..utils import file_hash, IOFromIterable

class MatchCandidate(object):
    def __init__(self, offset):
        self.offset = offset
        self.lines_matched = 1

def _apply_diff_seek(fileobj, offset, changes):
    if not changes:
        return

    fileobj.seek(offset)

    lines = list(fileobj)
    line_offset = changes[0][0] # XXX This only works with context
    old_i = 0
    new_i = 0
    for old, new, line in changes:
        if old is not None:
            old -= line_offset
        if new is not None:
            new -= line_offset

        if old is not None and new is None:
            del lines[old-1-old_i+new_i]
            old_i += 1
        elif old is None and new is not None:
            # TODO XXX we assume unix newlines here
            lines.insert(new-1, line+"\n")
            new_i += 1

    fileobj.seek(offset)
    for line in lines:
        fileobj.write(line)

def apply_diff(fileobj, changes):
    before_lines = [line[2] for line in changes if line[0] is not None]

    # TODO: This search works better with context, but
    # might not work well with "normal" diff
    candidates = []
    while True:
        line = fileobj.readline()
        if not line:
            break
        line_trim = line.rstrip('\r\n')

        dead = []
        for c in candidates:
            if before_lines[c.lines_matched] == line_trim:
                c.lines_matched += 1
            else:
                dead.append(c)

        for c in dead:
            candidates.remove(c)

        if line_trim == before_lines[0]:
            candidates.append(MatchCandidate(fileobj.tell()))

        for c in candidates:
            if c.lines_matched == len(before_lines) - 1:
                return _apply_diff_seek(fileobj, c.offset, changes)

    raise RuntimeError("Diff rejected, old not found")

class ContainerPatcher(object):
    def __init__(self, container, chdir, strip_dir):
        self.container = container
        self.chdir = chdir
        self.strip_dir = strip_dir
        self.files = {}
        self.file_idx = 0
        self.tempdir = tempfile.TemporaryDirectory()

    def __enter__(self):
        return self

    def __exit__(self, type, exc, tb):
        self.cleanup()

    def cleanup(self):
        self.tempdir.cleanup()

    def _load_file(self, fn):
        tstream, tstat = self.container.get_archive(fn)
        tf = IOFromIterable(tstream)

        with tarfile.open(fileobj=tf, mode="r|") as tin:
            while True:
                ti = tin.next()
                if ti is None:
                    break

                fn = os.path.join(os.path.dirname(fn), ti.name)
                if ti.isreg():
                    out_fn = os.path.join(self.tempdir.name, str(self.file_idx))
                    self.file_idx += 1

                    with open(out_fn, "wb") as fb:
                        shutil.copyfileobj(tin.extractfile(ti), fb)
                    self.files[fn] = out_fn
                else:
                    self.files[fn] = None

    def _diff_path(self, diff):
        path = diff.header.index_path or diff.header.new_path or diff.header.old_path
        if self.strip_dir > 0:
            for i in range(self.strip_dir):
                while path and path[0] == '/':
                    path = path[1:]

                idx = path.find("/")
                if idx < 0:
                    # XXX TODO error if we can't trim here
                    break
                path = path[idx+1:]
        else:
            while path and path[0] == '/':
                path = path[1:]

        return posixpath.join(self.chdir, path)

    def _apply_diff(self, diff):
        fn = self._diff_path(diff)
        working_fn = self.files.get(fn)
        if working_fn is None:
            raise RuntimeError("Does not exist or is not regular file")

        with open(working_fn, "r+") as f:
            apply_diff(f, diff.changes)

    def apply_patch(self, fn):
        with open(fn) as f:
            patch = f.read()

        diffs = []
        need_files = set()
        for diff in whatthepatch.parse_patch(patch):
            fn = self._diff_path(diff)
            if fn not in self.files:
                need_files.add(fn)
            diffs.append(diff)

        for fn in need_files:
            self._load_file(fn)

        for diff in diffs:
            self._apply_diff(diff)

    def save(self):
        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                for fn, fp in self.files.items():
                    tar.add(fp, arcname=fn)
            tf.seek(0)

            self.container.put_archive(
                path="/",
                data=tf
            )

class TaskPatch(Task, name="patch"):
    def run(self, job):
        value = job.template(self.value)

        chdir = "/"
        strip_dir = 0
        if isinstance(value, str):
            patch_file = value
        else:
            patch_file = value.get("src", value.get("file"))
            chdir = value.get("chdir", chdir)
            strip_dir = value.get("strip-dir", strip_dir)

        if os.path.isdir(patch_file):
            patch_files = [os.path.join(patch_file, fn) for fn in sorted(os.listdir(patch_file))]
        else:
            patch_files = [patch_file]

        container = job.create({
            'patches' : [file_hash('sha256', fn) for fn in patch_files]
        })

        with ContainerPatcher(container, chdir=chdir, strip_dir=strip_dir) as patcher:
            for fn in patch_files:
                patcher.apply_patch(fn)
            patcher.save()

        job.commit()
