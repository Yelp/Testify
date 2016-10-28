# -*- coding: utf-8 -*-
import itertools


def merge_dicts_of_sets(*dicts):
    """ Each value of each dictionary is expected to be a set.
    Merge together the values within the sets of each key across all dictionaries.
    returns a single dictionary with all the merged contents
    """
    merged = {}
    for k in set(itertools.chain.from_iterable(d.keys() for d in dicts)):
        merged[k] = set(itertools.chain.from_iterable(d.get(k, []) for d in dicts))
    return merged
