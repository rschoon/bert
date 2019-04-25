
from .yaml import YamlMarked

class BuildFailed(Exception):
    def __init__(self, msg=None, rc=0, job=None):
        self.msg = msg
        self.rc = rc
        self.job = job

    def __repr__(self):
        return "BuildFailed(msg={0.msg:r}, rc={0.rc})".format(self)

    def __str__(self):
        if self.rc != 0:
            return "{0.msg} ({0.rc})".format(self)
        else:
            return str(self.msg)

class ConfigFailed(BuildFailed):
    def __init__(self, msg=None, job=None, element=None):
        super().__init__(msg=msg, job=job)

        self.filename = None
        self.line = None
        self.column = None

        if element is not None and isinstance(element, YamlMarked):
            self.filename = element.filename
            self.line = element.line
            self.column = element.column

    def __str__(self):
        if self.filename is not None:
            if self.line is not None:
                if self.column:
                    fmt = "{0.filename}:{0.line}:{0.column}: {0.msg}"
                else:
                    fmt = "{0.filename}:{0.line}: {0.msg}"
            else:
                fmt = "{0.filename}: {0.msg}"
        else:
            fmt = "{0.msg}"
        return fmt.format(self)

class TemplateFailed(ConfigFailed):
    def __init__(self, msg=None, job=None, element=None, tse=None):
        super().__init__(msg=msg, job=job, element=element)

        if tse is not None:
            if tse.filename is not None:
                self.filename = tse.filename
                self.line = tse.lineno
            else:
                if self.line is not None and tse.lineno is not None:
                    self.line += tse.lineno
            self.column = None
