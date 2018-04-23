
import os

class BuildVars(dict):
    def __init__(self):
        super().__init__(env=os.environ)
