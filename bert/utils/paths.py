
from ..tasks import JobContextType

class LocalPath(JobContextType):
    def __init__(self, path, job):
        self.path = path
        self.job = job

    def __str__(self):
        return self.__fspath__()

    def __fspath__(self):
        return self.job.resolve_path(self.path)
