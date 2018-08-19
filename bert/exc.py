
class BuildFailed(Exception):
    def __init__(self, msg=None, rc=0):
        self.msg = msg
        self.rc = rc

    def __repr__(self):
        return "BuildFailed(msg={0.msg:r}, rc={0.rc})".format(self)

