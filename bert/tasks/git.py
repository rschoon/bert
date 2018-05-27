
import hashlib
import os
import re
import random
import subprocess
import tarfile
import tempfile

from . import Task
from ..utils import file_hash

RE_CACHE_SUB = re.compile(r'[^-_.A-Za-z0-9]+')

def make_cache_key(path):
    prefix = hashlib.sha256(path.encode('utf-8')).hexdigest()
    suffix = RE_CACHE_SUB.sub('', os.path.basename(path))
    if suffix:
        return "{}-{}".format(prefix, suffix)
    return prefix

def random_id():
    return "%x"%random.randrange(2**32)

class TaskGit(Task, name="git"):
    def setup(self):
        self.repo = self.value['repo']
        self.path = self.value.get('path') or self.value.get('dest')
        self.ref = self.value.get('ref', "master")

        self.cache_key = make_cache_key(self.repo)

    def run(self, job):
        src_path = os.path.join(job.cache_dir, self.cache_key)
        commit = self._run_git(src_path)

        container = job.create({
            'path' : self.path,
            'commit' : commit,
        })

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.add(src_path, arcname=self.path)
            tf.seek(0)

            container.put_archive(
                path="/",
                data=tf
            )

        job.commit()

    def _run_git(self, dest):
        if not os.path.isdir(dest):
            subprocess.check_call(["git", "clone", self.repo, dest])
        subprocess.check_call(["git", "fetch", self.repo, "--tags", self.ref], cwd=dest)
        try:
            subprocess.check_call(["git", "checkout", "FETCH_HEAD"], cwd=dest)
        except OSError as exc:
            print("Warning: %s not found, using FETCH_HEAD"%(self.ref,))
            subprocess.check_call(["git", "checkout", self.ref], cwd=dest)

        hashval = subprocess.check_output(["git", "log", "-1", "--format=%H"], cwd=dest)
        return hashval.decode('utf-8').strip()
