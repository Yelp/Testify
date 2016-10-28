# -*- coding: utf-8 -*-
from testify import assert_equals
from testify import TestCase
from testify.utils import dicts


class MergeDictsTest(TestCase):
    def test_empty(self):
        result = dicts.merge_dicts_of_sets()
        assert_equals(result, {})

    def test_one(self):
        result = dicts.merge_dicts_of_sets({"a": set([1, 2])})
        assert_equals(result, {"a": set([1, 2])})

    def test_merge_unique(self):
        result = dicts.merge_dicts_of_sets(
            {"a": set([1, 2]), "b": set([5])},
            {"a": set([1, 2, 3]), "b": set([5, 4])},
            {"c": set([6]), "a": set()}
        )
        assert_equals(result, {'a': set([1, 2, 3]), 'c': set([6]), 'b': set([4, 5])})
