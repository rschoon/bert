
import os

class BuildVars(dict):
    def __init__(self, job=None):
        super().__init__(env=os.environ)

        if job:
            self['config'] = job.config.vars()
            if job.stage:
                self['stage'] = job.stage.vars()
            self.update(job.saved_vars)

