
import hashlib
import io
import json
import os
import requests
import tempfile

from . import Task, TaskVar
from ..utils import file_hash, value_hash

class TaskFetch(Task, name="fetch"):
    """
    Fetch a value from a url and save as a file in the image or variable.
    """

    class Schema(object):
        url = TaskVar()
        params = TaskVar()
        method = TaskVar(default="GET")
        dest_var = TaskVar()
        json = TaskVar(default=False)
        dest = TaskVar()

    def run_with_values(self, job, url, params, method, dest_var, dest, **kwargs):
        is_json = kwargs.get("json")
        if method == "GET":
            call_req = requests.get
        elif method == "POST":
            call_req = requests.post
        else:
            raise ValueError("Can't handle method %s"%method)

        if dest_var is None and dest is None:
            raise ValueError("No destination given")

        sha256_h = hashlib.new("sha256")
        with tempfile.TemporaryFile() as tf:
            with call_req(url, params=params, stream=True) as resp:
                for chunk in resp.iter_content(chunk_size=None):
                    sha256_h.update(chunk)
                    tf.write(chunk)
    
            if dest_var is not None:
                tf.seek(0)

                var_val = tf.read().decode('utf-8')
                if is_json:
                    var_val = json.loads(var_val)
                job.set_var(dest_var, var_val)

            # XXX dest is not well tested
            if dest is not None:
                tf.seek(0)

                container = job.create({
                    'file_sha256' : sha256_h.hexdigest(),
                    'dest' : dest
                })

                container.put_archive(
                    path=dest,
                    data=tf
                )

                job.commit()
