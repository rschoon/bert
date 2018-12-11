
from collections import OrderedDict
from datetime import datetime

import yaml

__all__ = ['from_yaml', 'YamlType']

#
#
#

class YamlType(object):
    @property
    def filename(self):
        return self.yaml_mark.name

    @property
    def line(self):
        return self.yaml_mark.line

    @property
    def column(self):
        return self.yaml_mark.column

class YamlImmutable(YamlType):
    @classmethod
    def _raw_init(cls, val):
        for o in cls.__mro__[::-1]:
            if o is object:
                continue
            return o(val)

    def __new__(cls, val, loader=None, node=None):
        o = super().__new__(cls, cls._raw_init(val))
        o.yaml_mark = node.start_mark
        return o

class YamlMutable(YamlType):
    def __init__(self, val, loader=None, node=None):
        super().__init__(val)
        self.yaml_mark = node.start_mark

class YamlInt(YamlImmutable, int):
    pass

class YamlFloat(YamlImmutable, float):
    pass

class YamlStr(YamlImmutable, str):
    pass

class YamlBytes(YamlImmutable, bytes):
    pass

class YamlBool(YamlImmutable, int):
    @classmethod
    def _raw_init(cls, val):
        return bool(val)

class YamlDict(YamlMutable, OrderedDict):
    pass

class YamlDateTime(YamlMutable, datetime):
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
def _construct_yaml_bool(loader, node):
    return YamlInt(loader.construct_yaml_int(node), loader=loader, node=node)

@constructor('tag:yaml.org,2002:float')
def _construct_yaml_bool(loader, node):
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
    return yaml.load(obj, YamlLoader)
