
import collections
import os
import posixpath
import shutil
import tarfile
import tempfile

import whatthepatch

from . import Task, TaskVar
from ..utils import file_hash, IOFromIterable, LocalPath

class PatchError(Exception):
    pass

class PatchedFile(object):
    def __init__(self, filename, lines=None, eol=None):
        self.filename = filename
        self.eol = eol
        self.offset_moved = 0

        if lines is None:
            try:
                with open(self.filename, "r") as fileobj:
                    self.lines = list(self._load_lines(fileobj))
            except FileNotFoundError as exc:
                raise PatchError("%s does not exist" % self.filename) from exc
        else:
            self.lines = list(self._load_lines(lines))

    def _load_lines(self, lines):
        eol_count = collections.defaultdict(int)

        for line in lines:
            line_r = line.rstrip('\r\n')
            eol = line[len(line_r):]
            eol_count[eol] += 1
            yield line_r, eol

        if self.eol is None:
            if eol_count:
                self.eol = max(eol_count, key=lambda k: eol_count[k])
            else:
                self.eol = '\n'

    def save(self):
        if self.filename is None:
            return

        # TODO: Recall first changed line and offset, and only update starting from there
        with open(self.filename, "w") as fileobj:
            for line in self.lines:
                fileobj.write("%s%s" % line)

    def apply_diff(self, changes):
        if not changes:
            return

        # TODO: Handle lack of context in diff?
        before_lines = [line[2] for line in changes if line[0] is not None]
        before_start = changes[0][0] + self.offset_moved

        # best case is diff is exactly where we expect it
        if self._match_at(before_start, before_lines):
            return self._apply_at(before_start, 0, changes)

        # text likely moved, so start looking forward and backwards
        backward_at = forward_at = 0
        while before_start + forward_at < len(self.lines) or before_start + backward_at > 0:
            if before_start + forward_at < len(self.lines):
                forward_at += 1
                if self._match_at(before_start + forward_at, before_lines):
                    return self._apply_at(before_start, forward_at, changes)

            if before_start + backward_at > 0:
                backward_at -= 1
                if self._match_at(before_start + backward_at, before_lines):
                    return self._apply_at(before_start, backward_at, changes)

        raise PatchError("Patch rejected")

    def _match_at(self, lineno_start, lines):
        for linenum, line in enumerate(lines, start=lineno_start):
            try:
                orig = self.lines[linenum]
            except IndexError:
                return False

            if orig[0] != line:
                return False
        return True

    def _apply_at(self, offset, adj, changes):
        old_i = 0
        new_i = 0

        for change in changes:
            if change.old is not None and change.new is None:
                del self.lines[adj+change.old-old_i+new_i]
                old_i += 1
            elif change.old is None and change.new is not None:
                self.lines.insert(adj+change.new, (change.line, self.eol))
                new_i += 1

class Patch(object):
    def __init__(self, patch, strip_dir=0, chdir=None):
        self.root_dir = None
        self.file_lookup = None
        self.strip_dir = strip_dir
        self.chdir = chdir
        self.diffs = []
        self.files = set()

        for diff in whatthepatch.parse_patch(patch):
            fn = self._diff_path(diff)
            self.files.add(fn)
            self.diffs.append(diff)

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

        if self.chdir is not None:
            path = posixpath.join(self.chdir, path)
        return path

    def apply(self, root_dir=None, file_lookup=None):
        if file_lookup is None and root_dir is None:
            raise ValueError("Either root_dir or file_lookup must be provided")

        patched_files = {}
        for diff in self.diffs:
            if not diff.header:
                # Do we want to allow providing file explicitly to avoid this error?
                raise RuntimeError("Can't use this patch, no header.")

            fn_orig = fn = self._diff_path(diff)
            fn_adj = False

            if file_lookup is not None:
                fn = file_lookup.get(fn)
                fn_adj = True
            if root_dir is not None:
                fn = os.path.join(root_dir, fn)
                fn_adj = True

            if not fn_adj:
                raise RuntimeError("Path for changed %r not found" % fn_orig)

            pf = patched_files.get(fn)
            if pf is None:
                pf = patched_files[fn] = PatchedFile(fn)

            pf.apply_diff(diff.changes)

        for pf in patched_files.values():
            pf.save()

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
        if not os.path.isabs(fn):
            load_fn = os.path.join(self.chdir, fn)

        tstream, tstat = self.container.get_archive(load_fn)
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

    def apply_patch(self, fn):
        fn = os.fspath(fn)
        with open(fn) as f:
            p = Patch(f.read(), strip_dir=self.strip_dir)

        for fn in p.files:
            self._load_file(fn)

        p.apply(file_lookup=self.files)

    def save(self):
        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                for fn, fp in self.files.items():
                    if not os.path.isabs(fn):
                        fn = os.path.join(self.chdir, fn)
                    tar.add(fp, arcname=fn)
            tf.seek(0)

            self.container.put_archive(
                path="/",
                data=tf
            )

class TaskPatch(Task, name="patch"):
    class Schema:
        src = TaskVar('file', bare=True, help="Patch file to apply", type=LocalPath)
        chdir = TaskVar(default='/', help="Directory to apply patch from")
        strip_dir = TaskVar(default=0, help="Strip directory prefixes from patched filenames")

    def run_with_values(self, job, src, chdir, strip_dir):
        if os.path.isdir(src):
            patch_files = [os.path.join(src, fn) for fn in sorted(os.listdir(src))]
        else:
            patch_files = [src]

        container = job.create({
            'patches': [file_hash('sha256', fn) for fn in patch_files],
            'chdir': chdir,
            'strip_dir': strip_dir
        })

        with ContainerPatcher(container, chdir=chdir, strip_dir=strip_dir) as patcher:
            for fn in patch_files:
                patcher.apply_patch(fn)
            patcher.save()

        job.commit()
