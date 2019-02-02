
import hashlib
import io
import os
import requests
import tempfile

from . import Task
from ..utils import file_hash, value_hash

class TaskFetch(Task, name="fetch"):
    """
    Fetch a value from a url and save as a file in the image or variable.
    """

    def run(self, job):
        value = job.template(self.value)

        url = value["url"]
        params = value.get("params", {})
        method = value.get("method", "GET")
        dest_var = value.get("dest-var")
        is_json = value.get("json", False)
        dest = value.get("dest")

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
