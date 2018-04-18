
import hashlib
import tarfile
import tempfile

from . import Task
from ..utils import file_hash

RE_CACHE_SUB = re.compile(r'[^-_.A-Za-z0-9]+')

def make_cache_key(path):
    prefix = hashlib.sha256(path)
    suffix = RE_CACHE_SUB.sub('', os.path.basename(path))
    if suffix:
        return "{}-{}".format(prefix, suffix)
    return prefix

class TaskGit(Task, name="git"):
    def setup(self):
        self.repo = self.value['repo']
        self.depth = self.value.get('depth', None)
        self.path = self.value.get('path') or self.value.get('dest')
        self.tag = self.value.get('tag')
        self.branch = self.branch.get('branch')
        if not self.tag and not self.branch:
            self.branch = "master"

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
                tar.add(self.value)
            tf.seek(0)

            container.put_archive(
                path=job.work_dir,
                data=tf
            )

        job.commit()

    def _run_git(self, dest):
        opts = [self.repo]
        if self.tag:
            opts.append(self.tag+":target")
        else:
            opts.append(self.branch+":target")
        if self.depth:
            opts.extend(["--depth", str(self.depth)])

        if os.path.isdir(dest):
            subprocess.check_call(["git", "fetch"] + opts, cwd=dest)
        else:
            subprocess.check_call(["git", "clone"] + opts + [dest])
        subprocess.check_call(["git", "checkout", "target"], cwd=dest)

        hashval = subprocess.check_output(["git", "log", "-1", "--format=%H"], cwd=dest)
        return hashval.decode('utf-8').strip()
