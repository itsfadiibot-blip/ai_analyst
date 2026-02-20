# -*- coding: utf-8 -*-
import time

_FIELD_KB_CACHE = {
    'models': {},
    'fields': {},
    'synonym_index': {},
    'loaded_at': 0.0,
    'ttl_seconds': 3600,
}


def invalidate_field_kb_cache():
    _FIELD_KB_CACHE['models'] = {}
    _FIELD_KB_CACHE['fields'] = {}
    _FIELD_KB_CACHE['synonym_index'] = {}
    _FIELD_KB_CACHE['loaded_at'] = 0.0


def is_field_kb_cache_expired():
    loaded_at = _FIELD_KB_CACHE.get('loaded_at') or 0.0
    ttl = int(_FIELD_KB_CACHE.get('ttl_seconds') or 3600)
    return not loaded_at or (time.time() - loaded_at) >= ttl
