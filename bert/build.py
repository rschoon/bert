
from collections import OrderedDict
import copy
import docker
import dockerpty
import io
import posixpath
import jinja2
import json
import os

from .display import Display
from .filters import setup_filters
from .tasks import get_task
from .utils import json_hash, decode_bin
from .yaml import from_yaml, preserve_yaml_mark, get_yaml_type_name
from .exc import BuildFailed, ConfigFailed, TemplateFailed

LABEL_BUILD_ID = "bert.build_id"

class BuildResult(object):
    def __init__(self, vars=None):
        self.vars = vars or {}

class BuildImageExists(Exception):
    def __init__(self, image):
        self.image = image

#
#
#

def expect_type(val, type_):
    if type_ is None:
        return val
    return preserve_yaml_mark(type_(val), val)

def expect_list(val, subtype=None):
    if isinstance(val, list):
        return preserve_yaml_mark([expect_type(v, subtype) for v in val], val)
    if subtype is not None and isinstance(val, subtype):
        return preserve_yaml_mark([val], val)
    raise ConfigFailed("Invalid value type", element=val)

def expect_list_or_none(val, subtype=None):
    if val is None:
        return val
    return expect_list(val, subtype=subtype)

def copy_dict(val):
    return preserve_yaml_mark(OrderedDict(val), val)

def _make_environ_dict(envlist):
    return dict(e.split("=", 1) for e in envlist)

#
#
#

class ConfigGroup(object):
    def __init__(self, *configs):
        self._configs = configs

    @property
    def name(self):
        return ".".join(c.name for c in self._configs)

    def __reversed__(self):
        return reversed(self._configs)

    def __iter__(self):
        return iter(self._configs)

    def __len__(self):
        return len(self._configs)

def _chain_configs(root):
    configs = root.configs
    if not configs:
        yield None,
        return
    for config in configs:
        for c in _chain_configs(config):
            yield (config, *c)

def chain_configs(root):
    for c in _chain_configs(root):
        yield ConfigGroup(*c[:-1])

def build_stages(configs, stages, display, shell_fail=False, vars=None):
    saved_vars = {}
    if vars is not None:
        saved_vars.update(vars)

    for stage in stages:
        try:
            job = stage.build(configs, display, vars=saved_vars)
        except BuildFailed as bf:
            if shell_fail and bf.job is not None and bf.rc != 0:
                display.echo("Job failed, dropping into shell", err=True)
                bf.job.resurrect_shell()
            raise

        saved_vars = job.saved_vars
        job.close()
    return saved_vars

class BuildVars(dict):
    def __init__(self, job=None):
        super().__init__(env=os.environ)

        if job:
            job.put_global_vars(self)

class BertTask(object):
    def __init__(self, action, value=None, name=None, env=None, when=None, capture=None, capture_encoding=None, user=None, groups=None):
        self.name = name
        self.env = env
        self.user = user
        self.groups = groups
        self.when = when
        self.capture = capture
        self.capture_encoding = capture_encoding
        self._task = get_task(action, value)

    @classmethod
    def create_from_dict(cls, taskinfo):
        taskinfo = copy_dict(taskinfo)

        # this may be first instead of action
        name = taskinfo.pop("name", None)

        # action is always early
        action, value = taskinfo.popitem(last=False)

        # other props
        env = taskinfo.pop("env", None)
        when = taskinfo.pop("when", None)
        user = taskinfo.pop("user", None)
        group = taskinfo.pop("group", None)
        groups = taskinfo.pop("groups", None)
        capture = taskinfo.pop("capture", None)
        capture_encoding = taskinfo.pop("capture-encoding", "utf-8")

        if groups is not None and group is not None:
            groups.insert(0, group)
        elif group is not None:
            groups = [group]

        if taskinfo:
            raise ConfigFailed(
                "Unexpected attributes %r" % ", ".join(taskinfo.values()),
                element=taskinfo
            )

        try:
            return cls(action,
                       name=name, value=value, env=env, when=when,
                       user=user, groups=groups,
                       capture=capture, capture_encoding=capture_encoding)
        except ValueError as exc:
            raise ConfigFailed(str(exc), element=taskinfo)

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

        value = self._task.value
        if value is not None:
            if isinstance(value, (dict, list, set)):
                value = json.dumps(value)
            return "%s: %s" % (self.task_name, value)

        return self.task_name

    def run(self, job):
        job.display.echo(">>> Build: {}".format(self.display_name))

        if self.when is not None:
            if not job.eval_expr(self.when):
                job.display.echo("--- Skipped")
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
    def __init__(self, stage, configs, vars=None, work_dir=None, display=None):
        # XXX timeout is problematic
        self.docker_client = docker.from_env(timeout=600)

        self.tpl_env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        setup_filters(self.tpl_env)

        self.display = display
        self.stage = stage
        self.configs = configs
        self.changes = []
        self.work_dir = work_dir
        self.cache_dir = "cache"
        self.src_image = None
        self.current_task = None
        self._all_containers = []
        self._extra_images = []
        self.from_image_cache = stage.from_image_cache
        if vars is not None:
            self.saved_vars = vars
        else:
            self.saved_vars = {}
        self.vars = BuildVars(self)

    def setup(self, image):
        self.src_image = image

        self.display.echo(">>> Pulling: {}".format(self.src_image))
        img = self.from_image_cache.get(self.src_image)
        if img is None:
            img = self.from_image_cache[self.src_image] = self.docker_client.images.pull(self.src_image)

        if self.work_dir is None:
            wd = img.attrs["Config"].get("WorkingDir")
            if wd:
                self.work_dir = wd
            else:
                self.work_dir = "/"
        else:
            self.run_task(BertTask('set-image-attr', {'work-dir': self.work_dir}))

    def run_task(self, task):
        self.current_task = CurrentTask(task)
        task.run(self)

    def resolve_path(self, path):
        if os.path.isabs(path):
            return path
        return os.path.join(self.vars['bert_root_dir'], path)

    def tarfile_add(self, tf, srcname, arcname=None, recursive=True, template=False, template_encoding='utf-8', mode=None):
        if arcname is None:
            arcname = srcname
        paths = [(arcname, srcname)]

        while True:
            try:
                arcname, srcname = paths.pop()
            except IndexError:
                break

            ti = tf.gettarinfo(srcname, arcname)

            if mode is not None:
                ti.mode = (ti.mode & ~0o777) | mode

            if ti.isreg():
                if template:
                    with open(srcname, "r", encoding=template_encoding) as fi:
                        content = self.template(fi.read()).encode(template_encoding)
                        ti.size = len(content)
                        tf.addfile(ti, io.BytesIO(content))
                else:
                    with open(srcname, "rb") as fi:
                        tf.addfile(ti, fi)
            elif ti.isdir():
                tf.addfile(ti)
                if recursive:
                    for fn in sorted(os.listdir(srcname)):
                        paths.append((posixpath.join(arcname, fn), os.path.join(srcname, fn)))
            else:
                tf.addfile(ti)

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

        self.display.echo("--- Id: {}".format(key_id))

        if not self.current_task.task.capture:
            images = self.docker_client.images.list(filters={
                'label': '{}={}'.format(LABEL_BUILD_ID, key_id)
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
            labels={LABEL_BUILD_ID: key_id},
            command=command,
            working_dir=work_dir,
            user=self.current_task.task.user,
            group_add=self.current_task.task.groups,
            stdin_open=self.display.interactive,
            environment=["{}={}".format(*p) for p in env.items()],
            tty=self.display.interactive
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

        watch_result = canceled = None
        if self.current_task.command is not None:
            try:
                watch_result = self.display.watch_container(
                    self.docker_client,
                    container,
                    self.current_task.task.capture
                )
            except KeyboardInterrupt:
                canceled = True

            # If we were interrupted, we got here early and need to stop.
            # If not, we are stopped anyway.
            container.stop()

            # Determined if we were successful.
            result = container.wait()
            if result['StatusCode'] != 0:
                raise BuildFailed(rc=result['StatusCode'], job=self)

            if canceled:
                raise BuildFailed(rc=-1, job=self)

        conf = copy.deepcopy(container.image.attrs.get('Config', {}))

        changes = [
            "LABEL {}={}".format(LABEL_BUILD_ID, self.current_task.key_id)
        ]

        if env or self.current_task.task.env:
            new_env = _make_environ_dict(conf.get('Env', ()))

            if self.current_task.task.env:
                for item in self.current_task.task.env:
                    new_env[item] = ""

            if env:
                new_env.update(env)

            conf['Env'] = ["{}={}".format(k, v) for k, v in new_env.items()]

        # This can take a while...
        image = container.commit(
            changes="\n".join(changes),
            conf=conf
        )

        if self.current_task.task.capture is not None:
            self.set_var(
                self.current_task.task.capture,
                decode_bin(watch_result.stdout, self.current_task.task.capture_encoding)
            )

        self.changes.append(image.id)
        self.src_image = image.id
        self.current_task = None

        self.display.echo("--- New Image: {}".format(self.src_image))
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
                labels={LABEL_BUILD_ID: "@temporary"},
                working_dir=self.work_dir,
                stdin_open=True,
                environment=["{}={}".format(*p) for p in env.items()],
                tty=True,
                command="/bin/bash"  # XXX This is a guess!
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
        self.display.echo("--- Existing Image: {}".format(self.src_image))

    def eval_expr(self, txt):
        expr = self.tpl_env.compile_expression(txt)
        return expr(**self.vars)

    def template(self, txt):
        if txt is None or isinstance(txt, (int, float)):
            return txt

        if isinstance(txt, dict):
            return {self.template(k): self.template(v) for k, v in txt.items()}
        elif isinstance(txt, list):
            return [self.template(v) for v in txt]

        try:
            tpl = self.tpl_env.from_string(txt)
        except jinja2.TemplateSyntaxError as tse:
            raise TemplateFailed("Problem parsing template: {}".format(tse), element=txt, tse=tse)
        except jinja2.TemplateError as te:
            raise TemplateFailed("Problem parsing template: {}".format(te), element=txt)

        try:
            return tpl.render(**self.vars)
        except jinja2.UndefinedError as ue:
            raise TemplateFailed("Problem rendering template: {}".format(ue), element=txt)

    def set_var(self, name, value):
        self.vars[name] = self.saved_vars[name] = value

    def put_global_vars(self, data):
        for conf in self.configs:
            conf.put_global_vars(data)
        if self.stage:
            self.stage.put_global_vars(data)
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

    @property
    def root_dir(self):
        return self.parent_scope.root_dir

    def make_child_name(self, name):
        return name

    def load_global_vars(self, config):
        include_vars = expect_list_or_none(config.pop("include-vars", None), str)
        if include_vars:
            for inc_fn in include_vars:
                with open(os.path.join(self.root_dir, inc_fn), "r") as f:
                    self.global_vars.update(from_yaml(f))

        svars = config.pop('vars', None)
        if svars:
            if isinstance(svars, dict):
                self.global_vars.update(svars)
            else:
                raise ConfigFailed(
                    "Expected vars to be a mapping, but got {}".format(get_yaml_type_name(svars)),
                    element=svars
                )

    def put_global_vars(self, data):
        if self.parent_scope is not None:
            self.parent_scope.put_global_vars(data)
        data.update(self.global_vars)

class BertChildScope(BertScope):
    def make_child_name(self, name):
        return "{}.{}".format(self.name, name)

class BertConfig(BertChildScope):
    def __init__(self, data, parent=None):
        super().__init__(parent)

        if not isinstance(data, dict):
            raise ConfigFailed(
                "Expect config definition to be a mapping, but got {}".format(get_yaml_type_name(data)),
                element=data
            )

        data = copy_dict(data)
        self.load_global_vars(data)

        try:
            self.short_name = data.pop('name')
        except KeyError:
            raise ConfigFailed(
                "Config is missing required field name",
                element=data
            )

        self.name = self.short_name
        if parent is not None:
            self.name = parent.make_child_name(self.name)

        try:
            self.images = expect_list(data.pop("from"), str)
        except KeyError:
            self.images = None

        subconfigs = data.pop("configs", ())
        if subconfigs:
            self.configs = self.create_from_list(subconfigs)
        else:
            self.configs = None

    @classmethod
    def create_from_list(cls, configs, parent_scope=None):
        if not isinstance(configs, list):
            raise ConfigFailed(
                "Expect configs to be a list, but got {}".format(get_yaml_type_name(configs)),
                element=configs
            )

        return [BertConfig(confdata, parent_scope) for confdata in configs]

    def make_child_name(self, name):
        return "{}.{}".format(self.name, name)

    def put_global_vars(self, data):
        data['config'] = self.get_self_vars()
        super().put_global_vars(data)

    def get_self_vars(self):
        return {
            'name': self.name,
            'short_name': self.short_name,
            'source_images': self.images
        }

class BertStage(BertChildScope):
    def __init__(self, parent, data, name=None):
        super().__init__(parent)

        if not isinstance(data, dict):
            raise ConfigFailed(
                "Expect stage definition to be a mapping, but got {}".format(get_yaml_type_name(data)),
                element=data
            )

        data = copy_dict(data)

        self.name = self.short_name = name
        if parent is not None:
            self.name = parent.make_child_name(self.name)

        self.build_tag = data.pop("build-tag", None)
        self.work_dir = data.pop("work-dir", None)
        try:
            self.from_ = expect_list(data.pop("from"), str)
        except KeyError:
            self.from_ = None

        try:
            task_list = data.pop("tasks")
        except KeyError:
            raise ConfigFailed("Missing required task list", element=data)

        self.tasks = list(self._iter_parse_tasks(task_list))
        self.from_image_cache = parent.from_image_cache

        self.load_global_vars(data)

    def _iter_parse_tasks(self, tasks):
        tasks = expect_list(tasks, OrderedDict)
        for task in tasks:
            yield BertTask.create_from_dict(task)

    def build(self, configs, display=None, vars=None):
        vars = dict(vars) if vars else {}

        if self.from_:
            images = self.from_
        else:
            images = ()
            for config in reversed(configs):
                if config.images:
                    images = config.images
                    break

        if not images:
            raise ConfigFailed("Stage lacks images")

        display.echo("### Stage: {}/{}".format(configs.name, self.name))
        job = BuildJob(self, configs, vars=vars, work_dir=self.work_dir, display=display)
        for from_image in images:
            self._build_from(job, configs, from_image)

        return job

    def _build_from(self, job, configs, img):
        try:
            job.setup(img)
            for task in self.tasks:
                job.run_task(task)

            if self.build_tag:
                img = job.docker_client.images.get(job.src_image)
                img.tag(job.template(self.build_tag))
        finally:
            job.close()

    def put_global_vars(self, data):
        data['stage'] = self.get_self_vars()
        super().put_global_vars(data)

    def get_self_vars(self):
        return {
            'name': self.name,
            'short_name': self.short_name,
            'source_images': self.from_
        }

class BertBuild(BertScope):
    def __init__(self, filename, shell_fail=False, config=None, display=None, root_dir=None):
        super().__init__(None)

        if display is not None:
            self.display = display
        else:
            self.display = Display()

        if root_dir is None:
            if filename is not None:
                root_dir = os.path.dirname(filename)
            else:
                root_dir = '.'
        self._root_dir = root_dir

        self.filename = filename
        self.shell_fail = shell_fail
        self.configs = []
        self.stages = []
        self.from_image_cache = {}
        if config is not None:
            self.load_config(config)
        if self.filename is not None:
            self._parse()

    def __repr__(self):
        return "BertBuild(%r)" % (self.filename, )

    def _parse(self):
        with open(self.filename, "r") as f:
            config = from_yaml(f)
        self.load_config(config)

    def load_config(self, config):
        if not isinstance(config, dict):
            raise ConfigFailed(
                "Unexpected type at top level, got {}, expected a mapping".format(get_yaml_type_name(config)),
                element=config
            )

        self.load_global_vars(config)

        tasks = config.pop('tasks', None)
        stages = config.pop('stages', None)

        if tasks and stages:
            raise ConfigFailed(
                "Got both stages and tasks at top level, but only expected either.",
                element=tasks
            )
        elif tasks is None and stages is None:
            raise ConfigFailed(
                "Need one of tasks or stages at top level",
                element=config
            )

        if 'configs' in config:
            configs = config.pop("configs")
        else:
            configs = [{"name": "default"}]
            for name in ('from', ):
                try:
                    configs[0][name] = config.pop(name)
                except KeyError:
                    pass
        self.configs = BertConfig.create_from_list(configs, parent_scope=self)

        if tasks:
            self.stages.append(BertStage(self, {'tasks': tasks}, name='main'))
        else:
            for stage_name, stage in stages.items():
                stage = BertStage(self, stage, name=stage_name)
                self.stages.append(stage)

    @property
    def root_dir(self):
        return self._root_dir

    def put_global_vars(self, data):
        data['bert_root_dir'] = self.root_dir
        super().put_global_vars(data)

    def build(self, vars={}):
        output_global_vars = {}
        for configs in chain_configs(self):
            output_global_vars.update(build_stages(
                configs,
                self.stages,
                self.display,
                shell_fail=self.shell_fail,
                vars=vars
            ))
        return BuildResult(output_global_vars)
