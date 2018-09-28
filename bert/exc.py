
class BuildFailed(Exception):
    def __init__(self, msg=None, rc=0, job=None):
        self.msg = msg
        self.rc = rc
        self.job = job

    def __repr__(self):
        return "BuildFailed(msg={0.msg:r}, rc={0.rc})".format(self)

