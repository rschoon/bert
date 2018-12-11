
from collections import OrderedDict
import click
import docker
import dockerpty
import jinja2
import json
import os

from .tasks import get_task
from .utils import json_hash
from .yaml import from_yaml
from .exc import BuildFailed

LABEL_BUILD_ID = "bert.build_id"

class BuildImageExists(Exception):
    def __init__(self, image):
        self.image = image

#
#
#

def expect_type(val, type_):
    if type_ is None:
        return val
    return type_(val)

def expect_list(val, subtype=None):
    if isinstance(val, list):
        return [expect_type(v, subtype) for v in val]
    if subtype is not None and isinstance(val, subtype):
        return [val]
    raise ValueError("Invalid value type")

def expect_list_or_none(val, subtype=None):
    if val is None:
        return val
    return expect_list(val, subtype=subtype)

#
#
#

class BuildVars(dict):
    def __init__(self, job=None):
        super().__init__(env=os.environ)

        if job:
            job.put_vars(self)

class BertTask(object):
    def __init__(self, taskinfo):
        # this may be first instead of action
        self.name = taskinfo.pop("name", None)

        # action is always early
        action, value = taskinfo.popitem(last=False)

        # other props
        self.env = taskinfo.pop("env", None)
        self.when = taskinfo.pop("when", None)

        assert not taskinfo
        self._task = get_task(action, value)

    @property
    def task_name(self):
        return self._task.task_name

    @property
    def key_params(self):
        # Don't peak into child task, it is expected to provide details to .create()
        return {}

    @property
    def display_name(self):
        if self.name:
            return self.name
        if self._task.value is not None:
            return "%s: %s"%(self.task_name, self._task.value)
        return self.task_name

    def run(self, job):
        click.echo(">>> Build: {}".format(self.display_name))

        if self.when is not None:
            if not job.eval_expr(self.when):
                click.echo("--- Skipped")
                return

        try:
            return self._task.run(job)
        except BuildImageExists as bie:
            job._commit_from_image(bie.image)

class CurrentTask(object):
    def __init__(self, task):
        self.image = None
        self.key_id = None
        self.task = task
        self.container = None
        self.env = None
        self.command = None
        self.image = None

    @property
    def display_name(self):
        return self.task.display_name

    @property
    def image_command(self):
        image = self.image
        if not image:
            return None
        config = image.attrs.get("Config")
        if not config:
            return None
        return config.get("Cmd")

class BuildJob(object):
    def __init__(self, stage, config, vars=None, work_dir=None):
        # XXX timeout is problematic
        self.docker_client = docker.from_env(timeout=600)

        self.tpl_env = jinja2.Environment(undefined=jinja2.StrictUndefined)

        self.stage = stage
        self.config = config
        self.changes = []
        self.work_dir = "/bert-build" if work_dir is None else work_dir
        self.cache_dir = "cache"
        self.src_image = None
        self.current_task = None
        self._all_containers = []
        self._extra_images = []
        if vars is not None:
            self.saved_vars = vars
        else:
            self.saved_vars = {}
        self.vars = BuildVars(self)

    def setup(self, image, run_setup=True):
        self.src_image = image

        click.echo(">>> Pulling: {}".format(self.src_image))
        self.docker_client.images.pull(self.src_image)

        if run_setup:
            self.run_task(BertTask(OrderedDict(setup=None)))

    def run_task(self, task):
        self.current_task = CurrentTask(task)
        task.run(self)

    def create(self, job_key, command=None):
        if self.current_task is None:
            raise BuildFailed("Task Create: No current task")

        ct = self.current_task.task
        env = self._make_env()
        work_dir = self.work_dir

        key_params = {}
        if env:
            key_params["env"] = env
            key_params["work_dir"] = work_dir
        key_params.update(ct.key_params)

        key_id = self.current_task.key_id = json_hash('sha256', [
            self.src_image,
            ct.task_name,
            key_params,
            job_key
        ])

        click.echo("--- Id: {}".format(key_id))

        images = self.docker_client.images.list(filters={
            'label' : '{}={}'.format(LABEL_BUILD_ID, key_id)
        }, all=True)
        if images:
            raise BuildImageExists(images[0])

        image = self.src_image
        if isinstance(image, str):
            image = self.docker_client.images.get(self.src_image)
        self.current_task.image = image

        self.current_task.command = command
        self.current_task.env = env

        container = self.current_task.container = self.docker_client.containers.create(
            image=self.src_image,
            labels={LABEL_BUILD_ID : key_id},
            command=command,
            working_dir=work_dir,
            stdin_open=True,
            environment=["{}={}".format(*p) for p in env.items()],
            tty=True
        )
        return container

    def _make_env(self):
        env = {}

        ct_env = self.current_task.task.env
        if ct_env:
            for k, v in ct_env.items():
                env[self.template(k)] = self.template(v)

        return env

    def commit(self, env=None):
        if self.current_task is None:
            raise BuildFailed("Task Commit: No current task", job=self)

        container = self.current_task.container
        if container is None:
            raise BuildFailed("Task Commit: No current container to commit", job=self)

        if self.current_task.command is not None:
            try:
                dockerpty.start(self.docker_client.api, container.id)
            except KeyboardInterrupt:
                pass

            # If we were interrupted, we got here early and need to stop.
            # If not, we are stopped anyway.
            container.stop()

            # Determined if we were successful.
            result = container.wait()
            if result['StatusCode'] != 0:
                raise BuildFailed(rc=result['StatusCode'], job=self)

        changes = [
            "LABEL {}={}".format(LABEL_BUILD_ID, self.current_task.key_id) 
        ]

        cmd = self.current_task.image_command
        if cmd and self.current_task.command:
            changes.append("CMD {}".format(json.dumps(cmd)))

        if env:
            for ek, ev in env.items():
                changes.append("ENV {} {}".format(ek, ev))

        # This can take a while...
        image = container.commit(
            changes="\n".join(changes)
        )

        self.changes.append(image.id)
        self.src_image = image.id
        self.current_task = None

        click.echo("--- New Image: {}".format(self.src_image))
        self.cleanup()

    def resurrect_shell(self, container=None, env=None):
        if container is None:
            container = self.current_task.container
            if env is None:
                env = self.current_task.env

        # once the command is stopped, there's no getting it back without
        # running the command again, but we can commit to an image
        image = container.commit(
            changes="LABEL {}={}".format(LABEL_BUILD_ID, "@temporary")
        )
        self._extra_images.append(image)

        try:
            container = self.docker_client.containers.create(
                image=image,
                labels={LABEL_BUILD_ID : "@temporary"},
                working_dir=self.work_dir,
                stdin_open=True,
                environment=["{}={}".format(*p) for p in env.items()],
                tty=True,
                command="/bin/bash" # XXX This is a guess!
            )
            self._all_containers.append(container)

            try:
                dockerpty.start(self.docker_client.api, container.id)
            finally:
                container.stop()
        finally:
            self.cleanup()

    def cancel(self):
        self.current_container = None
        self.current_command = None
        self.cleanup()

    def _commit_from_image(self, image):
        self.src_image = image.id
        click.echo("--- Existing Image: {}".format(self.src_image))

    def eval_expr(self, txt):
        expr = self.tpl_env.compile_expression(txt)
        return expr(**self.vars)

    def template(self, txt):
        if txt is None or isinstance(txt, (int, float)):
            return txt

        if isinstance(txt, dict):
            return {self.template(k):self.template(v) for k,v in txt.items()}
        elif isinstance(txt, list):
            return [self.template(v) for v in txt]

        tpl = self.tpl_env.from_string(txt)
        return tpl.render(**self.vars)

    def set_var(self, name, value):
        self.vars[name] = self.saved_vars[name] = value

    def put_vars(self, data):
        self.config.put_vars(data)
        if self.stage:
            self.stage.put_vars(data)
        data.update(self.saved_vars)

    def cleanup(self):
        current_container = None
        if self.current_task is not None and self.current_task.task is not None:
            current_container = self.current_task.container

        for container in self._all_containers[::-1]:
            if container == current_container:
                continue
            container.remove()
            self._all_containers.remove(container)

        for image in self._extra_images:
            self.docker_client.images.remove(image.id, noprune=True)
        self._extra_images[:] = []

    def close(self):
        self.current_container = None
        self.cleanup()

#
#
#

class BertScope(object):
    def __init__(self, parent_scope=None):
        self.parent_scope = parent_scope
        self.global_vars = {}

    def load_global_vars(self, config):
        include_vars = expect_list_or_none(config.pop("include-vars", None), str)
        if include_vars:
            for inc_fn in include_vars:
                with open(inc_fn, "r") as f:
                    self.global_vars.update(from_yaml(f))

        svars = config.pop('vars', None)
        if svars:
            self.global_vars.update(svars)

    def put_vars(self, data):
        if self.parent_scope is not None:
            self.parent_scope.put_vars(data)
        data.update(self.global_vars)

class BertConfig(BertScope):
    def __init__(self, data):
        super().__init__(None)

        self.load_global_vars(data)

        self.name = data.pop('name')
        try:
            self.images = expect_list(data.pop("from"), str)
        except KeyError:
            self.images = None

    def build_stages(self, stages, shell_fail=False):
        saved_vars = {}
        for stage in stages:
            try:
                job = stage.build(self, vars=saved_vars)
            except BuildFailed as bf:
                if shell_fail and bf.job is not None and bf.rc != 0:
                    click.echo("Job failed, dropping into shell", err=True)
                    bf.job.resurrect_shell()
                raise

            saved_vars = job.saved_vars
            job.close()

    def put_vars(self, data):
        data["config"] = {
            'name' : self.name,
            'images' : self.images
        }
        super().put_vars(data)

class BertStage(BertScope):
    def __init__(self, parent, data, name=None):
        super().__init__(parent)

        self.name = name
        self.build_tag = data.pop("build-tag", None)
        self.run_setup = data.pop("run-setup", True)
        self.work_dir = data.pop("work-dir", None)
        try:
            self.from_ = expect_list(data.pop("from"), str)
        except KeyError:
            self.from_ = None
        self.tasks = list(self._iter_parse_tasks(data.pop("tasks")))

        self.load_global_vars(data)

    def _iter_parse_tasks(self, tasks):
        tasks = expect_list(tasks, OrderedDict)
        for task in tasks:
            yield BertTask(task)

    def build(self, config, vars=None):
        vars = dict(vars) if vars else {}

        if self.from_:
            images = self.from_
        else:
            images = config.images

        job = BuildJob(self, config, vars=vars, work_dir=self.work_dir)

        for from_image in images:
            self._build_from(job, config, from_image)

        return job

    def _build_from(self, job, config, img):
        try:
            job.setup(img, run_setup=self.run_setup)
            for task in self.tasks:
                job.run_task(task)

            if self.build_tag:
                img = job.docker_client.images.get(job.src_image)
                img.tag(job.template(self.build_tag))
        finally:
            job.close()

    def put_vars(self, data):
        if "stage" not in data:
            data["stage"] = {
                'name' : self.name,
                'images' : self.from_
            }
        super().put_vars(data)

class BertBuild(BertScope):
    def __init__(self, filename, shell_fail=False):
        super().__init__(None)

        self.filename = filename
        self.shell_fail = shell_fail
        self.configs = []
        self.stages = []
        self._parse()

    def __repr__(self):
        return "BertBuild(%r)"%(self.filename, )

    def _parse(self):
        with open(self.filename, "r") as f:
            config = from_yaml(f)

        self.load_global_vars(config)

        if 'tasks' in config:
            self.configs.append(BertConfig({
                'name' : 'default'
            }))
            self.stages.append(BertStage(self, config))
        else:
            if 'configs' in config:
                configs = config.pop("configs")
            else:
                configs = [{"name" : "default"}]
                for name in ('from', ):
                    try:
                        configs[0][name] = config.pop(name)
                    except KeyError:
                        pass

            for confdata in configs:
                conf = BertConfig(confdata)
                self.configs.append(conf)

            stages = config.pop("stages")
            for stage_name, stage in stages.items():
                stage = BertStage(self, stage, name=stage_name)
                self.stages.append(stage)

    def build(self):
        for config in self.configs:
            config.build_stages(self.stages, shell_fail=self.shell_fail)
