# -*- coding: UTF-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import sys

import testify as T
from testify.contrib.doctestcase import DocTestCase


def foo(bar):
    """
    >>> foo(1)
    1
    >>> foo(2)
    4
    """
    return bar * bar


class TestNoPollutionDocTestCase(T.TestCase):
    def test_doc_test_case_doesnt_pollute(self):
        class MyDocTestCase(DocTestCase):
            module = sys.modules[foo.__module__]

        MyDocTestCase().run()
        T.assert_not_in('_', __builtins__)
