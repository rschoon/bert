
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

class GitRun(object):
    def __init__(self, job, repo, path, ref):
        self.job = job
        self.repo = job.template(repo)
        self.path = job.template(path)
        self.ref = job.template(ref)

        self.src_path = os.path.join(job.cache_dir, make_cache_key(self.repo))

    def run(self):
        commit = self.run_git()

        container = self.job.create({
            'path' : self.path,
            'commit' : commit,
        })

        with tempfile.TemporaryFile() as tf:
            with tarfile.open(fileobj=tf, mode="w") as tar:
                tar.add(self.src_path, arcname=self.path)
            tf.seek(0)

            container.put_archive(
                path="/",
                data=tf
            )

        self.job.commit()

    def have_static_ref(self, dest, ref):
        """
        Determine is a reference is a tag or commit hash which
        should not change.
        """
        if subprocess.call(["git", "show-ref", "-q", "--verify", "refs/tags/"+ref], cwd=dest) == 0:
            return True
        if subprocess.call(["git", "rev-parse", "-q", "--verify", ref+"^{commit}"], cwd=dest) == 0:
            return True
        return False

    def run_git(self, dest=None):
        have_fetch_head = True

        if dest is None:
            dest = self.src_path

        if not os.path.isdir(dest):
            subprocess.check_call(["git", "clone", self.repo, dest])

        if self.have_static_ref(dest, self.ref):
            have_fetch_head = False
        else:
            try:
                subprocess.check_call(["git", "fetch", self.repo, "--tags", self.ref], cwd=dest)
            except subprocess.CalledProcessError:
                have_fetch_head = False
                # Some git repos forbit fetching via a commit hash, so retry
                # with everything
                print("Warning: fetching %s directly failed"%(self.ref, ))
                subprocess.check_call(["git", "fetch", self.repo], cwd=dest)

            try:
                if have_fetch_head:
                    subprocess.check_call(["git", "checkout", "FETCH_HEAD"], cwd=dest)
            except subprocess.CalledProcessError:
                print("Warning: %s not found at FETCH_HEAD, retrying directly"%(self.ref,))
                have_fetch_head = False

        if not have_fetch_head:
            subprocess.check_call(["git", "checkout", self.ref], cwd=dest)

        hashval = subprocess.check_output(["git", "log", "-1", "--format=%H"], cwd=dest)
        return hashval.decode('utf-8').strip()

class TaskGit(Task, name="git"):
    def setup(self):
        self.repo = self.value['repo']
        self.path = self.value.get('path') or self.value.get('dest')
        self.ref = self.value.get('ref', "master")

    def run(self, job):
        gr = GitRun(job, self.repo, self.path, self.ref)
        gr.run()
