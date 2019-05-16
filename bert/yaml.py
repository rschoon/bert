
from collections import OrderedDict
from datetime import datetime

import yaml

from . import exc

__all__ = ['from_yaml', 'YamlMarked', 'preserve_yaml_mark', 'get_yaml_type_name']

#
#
#

YAML_TYPE_MAP = {}

class YamlMarked(object):
    @property
    def filename(self):
        return self.yaml_mark.name

    @property
    def line(self):
        return self.yaml_mark.line + 1

    @property
    def column(self):
        return self.yaml_mark.column

class YamlVoid(YamlMarked):
    def __init__(self, mark=None):
        self.yaml_mark = mark

class YamlType(YamlMarked):
    TYPE_NAME = "UNKNOWN"

    @classmethod
    def __init_subclass__(cls, **kwargs):
        type_name = kwargs.pop('type_name', None)
        base_type = kwargs.pop('base_type', None)
        if base_type is None:
            for i, klass in enumerate(reversed(cls.mro())):
                if i == 1 and klass is not YamlType:
                    base_type = klass
                    break

        super().__init_subclass__(**kwargs)

        auto_type_name = None
        if base_type is not None:
            if isinstance(base_type, tuple):
                auto_type_name = base_type[0].__name__
                for b in base_type:
                    YAML_TYPE_MAP[b] = cls
            else:
                YAML_TYPE_MAP[base_type] = cls
                auto_type_name = base_type.__name__

        if type_name is not None:
            cls.TYPE_NAME = type_name
        elif auto_type_name is not None:
            cls.TYPE_NAME = auto_type_name

class YamlImmutable(YamlType):
    @classmethod
    def _raw_init(cls, val):
        for o in cls.__mro__[::-1]:
            if o is object:
                continue
            return o(val)

    def __new__(cls, val, loader=None, node=None, mark=None):
        o = super().__new__(cls, cls._raw_init(val))
        if mark is not None:
            o.yaml_mark = mark
        else:
            o.yaml_mark = node.start_mark
        return o

class YamlMutable(YamlType):
    def __init__(self, val, loader=None, node=None, mark=None):
        super().__init__(val)
        if mark is not None:
            self.yaml_mark = mark
        else:
            self.yaml_mark = node.start_mark

class YamlInt(YamlImmutable, int, type_name='integer'):
    pass

class YamlFloat(YamlImmutable, float):
    pass

class YamlStr(YamlImmutable, str, type_name='string'):
    pass

class YamlBytes(YamlImmutable, bytes):
    pass

class YamlBool(YamlImmutable, int, base_type=bool, type_name='boolean'):
    @classmethod
    def _raw_init(cls, val):
        return bool(val)

class YamlDict(YamlMutable, OrderedDict, base_type=(dict, OrderedDict), type_name='mapping'):
    pass

class YamlDateTime(YamlMutable, datetime, base_type=datetime):
    pass

class YamlSet(YamlMutable, set):
    pass

class YamlList(YamlMutable, list):
    pass

#
#
#

class YamlLoader(yaml.SafeLoader):
    pass

def constructor(tag):
    def dec(func):
        YamlLoader.add_constructor(tag, func)
        return func
    return dec

@constructor('tag:yaml.org,2002:map')
@constructor('tag:yaml.org,2002:omap')
def _construct_mapping(loader, node):
    loader.flatten_mapping(node)
    return YamlDict(loader.construct_pairs(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:str')
def _construct_yaml_str(loader, node):
    return YamlStr(loader.construct_scalar(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:bool')
def _construct_yaml_bool(loader, node):
    return YamlBool(loader.construct_yaml_bool(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:int')
def _construct_yaml_int(loader, node):
    return YamlInt(loader.construct_yaml_int(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:float')
def _construct_yaml_float(loader, node):
    return YamlFloat(loader.construct_yaml_float(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:binary')
def _contruct_yaml_binary(loader, node):
    return YamlBytes(loader.construct_yaml_binary(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:timestamp')
def _construct_yaml_timestamp(loader, node):
    return YamlDateTime(loader.construct_yaml_timestamp(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:set')
def _construct_yaml_set(loader, node):
    return YamlSet(loader.construct_yaml_set(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:pairs')
def _construct_yaml_pairs(loader, node):
    return YamlList(loader.construct_pairs(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:seq')
def _construct_yaml_seq(loader, node):
    return YamlList(loader.construct_sequence(node), loader=loader, node=node)

#
#
#

def from_yaml(obj):
    try:
        return yaml.load(obj, YamlLoader)
    except yaml.YAMLError as ye:
        if hasattr(ye, "problem_mark"):
            raise exc.ConfigFailed(ye.problem, element=YamlVoid(ye.problem_mark))
        else:
            raise exc.ConfigFailed(str(ye))

def get_yaml_type_name(obj):
    if isinstance(obj, YamlType):
        return obj.TYPE_NAME
    return type(obj).__name__

def preserve_yaml_mark(dst, src):
    if isinstance(src, YamlType):
        ycls = YAML_TYPE_MAP[type(dst)]
        return ycls(dst, mark=src.yaml_mark)
    return dst
