
import hashlib
import itertools
import json
import posixpath
import re

FILTERS = {}

def register_filter(func):
    FILTERS[func.__name__] = func
    return func

def setup_filters(tpl_env):
    tpl_env.filters.pop("tojson", None)
    tpl_env.filters.pop("safe", None)

    tpl_env.filters.update(FILTERS)

#
#
#

@register_filter
def dirname(path):
    return posixpath.dirname(path)

@register_filter
def basename(path):
    return posixpath.basename(path)

@register_filter
def dict2items(d):
    return [{'key' : k, 'value' : v} for k,v in d.items()]

def _items2dict(item):
    if isinstance(item, dict):
        return item['key'], item['value']
    return tuple(item)

@register_filter
def items2dict(items):
    return dict(_items2dict(item) for item in items)

register_filter(zip)
register_filter(itertools.zip_longest)

@register_filter
def hash(val, name):
    if isinstance(val, str):
        val = val.encode('utf-8')
    return hashlib.new(name, val).hexdigest()

@register_filter
def combine(*dicts, recursive=False):
    rv = {}
    for d in dicts:
        if recursive:
            for k,v in d.items():
                if isinstance(rv.get(k), dict) and isinstance(v, dict):
                    rv[k] = dict(rv[k])
                    rv[k].update(v)
                else:
                    rv[k] = v
        else:
            rv.update(d)
    return rv

def _regex(regex, multiline=False, ignorecase=False):
    flags = 0
    if multiline:
        flags |= re.MULTILINE
    if ignorecase:
        flags |= re.IGNORECASE
    return re.compile(regex, flags=flags)

@register_filter
def regex_search(s, regex, default="", **kwargs):
    m  = _regex(regex, **kwargs).search(s)
    if m is None:
        return default
    try:
        return m.group(1)
    except IndexError:
        return m.group(0)

@register_filter
def regex_findall(s, regex, **kwargs):
    return _regex(regex, **kwargs).findall(s)

@register_filter
def regex_replace(s, regex, replace, **kwargs):
    return _regex(regex, **kwargs).sub(replace, s)

@register_filter
def to_json(d):
    return json.dumps(d)

@register_filter
def from_json(d):
    return json.loads(d)
