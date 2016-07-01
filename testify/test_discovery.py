# Copyright 2009 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import inspect
import os
import pkgutil
import sys
import traceback
import unittest
from .test_case import MetaTestCase, TestifiedUnitTest
from .exceptions import DiscoveryError


def to_module(path):
    path = os.path.relpath(path)

    if path.startswith('..'):
        raise DiscoveryError('Test outside of current directory')

    path = path.replace(os.sep, '.')
    path_parts = path.split('.')
    if path_parts[-1] == 'py':
        path_parts.pop()
    return '.'.join(path_parts)


def get_parent_module_suites(mod):
    parent_mod_path, _, _ = mod.__name__.rpartition('.')
    if not parent_mod_path:
        return set()
    else:
        return set(getattr(sys.modules[parent_mod_path], '_suites', set()))


def get_test_classes_from_module(mod):
    mod._suites = (
        set(getattr(mod, '_suites', set())) | get_parent_module_suites(mod)
    )

    for _, cls in inspect.getmembers(mod, inspect.isclass):
        # Skip things that are only there due to a side-effect of importing
        if cls.__module__ != mod.__name__:
            continue

        # Skip tests that have __test __ = False
        if not cls.__dict__.get('__test__', True):
            continue

        if isinstance(cls, MetaTestCase):
            cls._suites = set(getattr(cls, '_suites', set())) | mod._suites
            yield cls
        elif issubclass(cls, unittest.TestCase):
            yield TestifiedUnitTest.from_unittest_case(
                cls, module_suites=mod._suites,
            )


def discover(what):
    """Given a string module path, drill into it for its TestCases.

    This will descend recursively into packages and lists, so the following are valid:
        - add_test_module('tests.biz_cmds.biz_ad_test')
        - add_test_module('tests.biz_cmds.biz_ad_test.tests')
        - add_test_module('tests.biz_cmds')
        - add_test_module('tests')
    """
    try:
        what = to_module(what)
        mod = __import__(what, fromlist=[str('__trash')])
        for cls in get_test_classes_from_module(mod):
            yield cls

        if not hasattr(mod, '__path__'):
            return

        # It's a package!
        for _, module_name, _ in pkgutil.walk_packages(
            mod.__path__,
            prefix=mod.__name__ + '.',
        ):
            submod = __import__(module_name, fromlist=[str('__trash')])
            for cls in get_test_classes_from_module(submod):
                yield cls
    except GeneratorExit:
        raise
    except BaseException:
        # print the traceback to stderr, or else we can't see errors during --list-tests > testlist
        traceback.print_exc()
        raise DiscoveryError(
            (
                '\n    ' +
                traceback.format_exc().replace('\n', '\n    ')
            ).rstrip()
        )


def import_test_class(module_path, class_name):
    for klass in discover(module_path):
        if klass.__name__ == class_name:
            return klass

    raise DiscoveryError(class_name)
