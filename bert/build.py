
from collections import OrderedDict
import click
import docker
import dockerpty
from jinja2 import Template
import json
import yaml

from .tasks import get_task
from .utils import json_hash
from .vars import BuildVars

LABEL_BUILD_ID = "bert.build_id"

class BuildImageExists(Exception):
    def __init__(self, image):
        self.image = image

class BuildFailed(Exception):
    def __init__(self, msg=None, rc=0):
        self.msg = msg
        self.rc = rc

    def __repr__(self):
        return "BuildFailed(msg={0.msg:r}, rc={0.rc})".format(self)

#
#
#

class YamlLoader(yaml.SafeLoader):
    pass

def _construct_yaml_mapping(loader, node):
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node))

YamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                           _construct_yaml_mapping)

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

#
#
#

class BertTask(object):
    def __init__(self, taskinfo):
        # this may be first instead of action
        self.name = taskinfo.pop("name", None)

        # action is always early
        action, value = taskinfo.popitem(last=False)

        # other props
        self.env = taskinfo.pop("env", None)

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
    def __init__(self, stage, config, vars=None):
        # XXX timeout is problematic
        self.docker_client = docker.from_env(timeout=600)

        self.stage = stage
        self.config = config
        self.changes = []
        self.work_dir = "/bert-build"
        self.cache_dir = "cache"
        self.src_image = None
        self.current_task = None
        self._all_containers = []
        if vars is not None:
            self.saved_vars = vars
        else:
            self.saved_vars = {}
        self.vars = BuildVars(self)

    def setup(self, image):
        self.src_image = image

        click.echo(">>> Pulling: {}".format(self.src_image))
        self.docker_client.images.pull(self.src_image)

        self.run_task(BertTask(OrderedDict(setup=None)))

    def run_task(self, task):
        self.current_task = CurrentTask(task)
        task.run(self)

    def create(self, job_key, command=None):
        if self.current_task is None:
            raise BuildFailed("Task Create: No current task")

        ct = self.current_task.task
        env = self._make_env()

        key_params = {}
        if env:
            key_params["env"] = env
        key_params.update(ct.key_params)

        key_id = self.current_task.key_id = json_hash('sha256', [
            self.src_image,
            ct.task_name,
            key_params,
            job_key
        ])

        click.echo(">>> Build: {}".format(self.current_task.display_name))
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
        container = self.current_task.container = self.docker_client.containers.create(
            image=self.src_image,
            labels={LABEL_BUILD_ID : key_id},
            command=command,
            working_dir=self.work_dir,
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
            raise BuildFailed("Task Commit: No current task")

        container = self.current_task.container
        if container is None:
            raise BuildFailed("Task Commit: No current container to commit")

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
                raise BuildFailed(rc=result['StatusCode'])

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

    def cancel(self):
        self.current_container = None
        self.current_command = None
        self.cleanup()

    def _commit_from_image(self, image):
        self.src_image = image.id
        click.echo("--- Existing Image: {}".format(self.src_image))

    def template(self, txt):
        if txt is None:
            return txt
        tpl = Template(txt)
        return tpl.render(**self.vars)

    def set_var(self, name, value):
        self.vars[name] = self.saved_vars[name] = value

    def cleanup(self):
        current_container = None
        if self.current_task is not None and self.current_task.task is not None:
            current_container = self.current_task.container

        for container in self._all_containers[::-1]:
            if container == current_container:
                continue
            self.docker_client.remove_container(container)
            self._all_containers.remove(container)

    def close(self):
        self.current_container = None
        self.cleanup()

#
#
#

class BertConfig(object):
    def __init__(self, data):
        self.name = data.pop('name')
        try:
            self.images = expect_list(data.pop("from"), str)
        except KeyError:
            self.images = None

    def build_stages(self, stages):
        saved_vars = {}
        for stage in stages:
            job = stage.build(self, vars=saved_vars)
            saved_vars = job.saved_vars

    def vars(self):
        return {
            'name' : self.name,
            'images' : self.images
        }

class BertStage(object):
    def __init__(self, data, name=None):
        self.name = name
        self.build_tag = data.pop("build-tag", None)
        try:
            self.from_ = expect_list(data.pop("from"), str)
        except KeyError:
            self.from_ = None
        self.tasks = list(self._iter_parse_tasks(data.pop("tasks")))

    def _iter_parse_tasks(self, tasks):
        tasks = expect_list(tasks, OrderedDict)
        for task in tasks:
            yield BertTask(task)

    def build(self, config, vars=None):
        if self.from_:
            images = self.from_
        else:
            images = config.images

        job = BuildJob(self, config, vars=vars)

        for from_image in images:
            self._build_from(job, config, from_image)

        return job

    def _build_from(self, job, config, img):
        try:
            job.setup(img)
            for task in self.tasks:
                job.run_task(task)

            if self.build_tag:
                img = job.docker_client.images.get(job.src_image)
                img.tag(job.template(self.build_tag))
        finally:
            job.close()

    def vars(self):
        return {
            'name' : self.name,
            'images' : self.from_
        }

class BertBuild(object):
    def __init__(self, filename):
        self.filename = filename
        self.configs = []
        self.stages = []
        self._parse()

    def __repr__(self):
        return "BertBuild(%r)"%(self.filename, )

    def _parse(self):
        with open(self.filename, "r") as f:
            config = yaml.load(f, YamlLoader)

            if 'tasks' in config:
                self.configs.append(BertConfig({
                    'name' : 'default'
                }))
                self.stages.append(BertStage(config))
            else:
                if 'configs' in config:
                    configs = config.pop("configs")
                else:
                    configs = [{"name" : "default"}]
                    for name in ('from', ):
                        try:
                            configs["default"][name] = config.pop(name)
                        except KeyError:
                            pass

                for confdata in configs:
                    conf = BertConfig(confdata)
                    self.configs.append(conf)

                stages = config.pop("stages")
                for stage_name, stage in stages.items():
                    stage = BertStage(stage, name=stage_name)
                    self.stages.append(stage)

    def build(self):
        for config in self.configs:
            config.build_stages(self.stages)

    def vars(self):
        return {}
