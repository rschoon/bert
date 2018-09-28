
class BuildFailed(Exception):
    def __init__(self, msg=None, rc=0, current_container=None, current_container_env=None):
        self.msg = msg
        self.rc = rc
        self.current_container = current_container
        self.current_container_env = current_container_env

    def __repr__(self):
        return "BuildFailed(msg={0.msg:r}, rc={0.rc})".format(self)

