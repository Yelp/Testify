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
import logging
import os
import sys
import time
import traceback
import types
import unittest
from test_case import MetaTestCase, TestifiedUnitTest
from errors import TestifyError

_log = logging.getLogger('testify')

class DiscoveryError(TestifyError): pass

def gather_test_paths(testing_dir):
    """Given a directory path, yield up paths for all py files inside of it"""
    for adir, subdirs, subfiles in os.walk(testing_dir):
        # ignore .svn directories and other such hiddens
        if adir.startswith('.'):
            continue
        for subfile in subfiles:
            # ignore __init__ files, dotfiles, etc
            if subfile.endswith('.py') and not (subfile.startswith('__init__.') or subfile.startswith('.')):
                relative_path = os.path.realpath(adir)[len(os.getcwd()) + 1:]
                fs_path = os.path.join(relative_path, subfile)
                yield fs_path[:-3].replace('/','.')

def discover(what):
    """Given a string module path, drill into it for its TestCases.

    This will descend recursively into packages and lists, so the following are valid:
        - add_test_module('tests.biz_cmds.biz_ad_test')
        - add_test_module('tests.biz_cmds.biz_ad_test.tests')
        - add_test_module('tests.biz_cmds')
        - add_test_module('tests')
    """

    def discover_inner(locator, suites=None):
        suites = suites or []
        if isinstance(locator, basestring):
            import_error = None
            try:
                test_module = __import__(locator)
            except (ValueError, ImportError), e:
                import_error = e
                _log.info('discover_inner: Failed to import %s: %s' % (locator, e))
                if os.path.isfile(locator) or os.path.isfile(locator+'.py'):
                    here = os.path.abspath(os.path.curdir) + os.path.sep
                    new_loc = os.path.abspath(locator)
                    if not new_loc.startswith(here):
                        raise DiscoveryError('Can only load modules by path within the current directory')

                    new_loc = new_loc[len(here):]
                    new_loc = new_loc.rsplit('.py',1)[0] #allows for .pyc and .pyo as well
                    new_loc = new_loc.replace(os.sep,'.')
                    try:
                        test_module = __import__(new_loc)
                        locator = new_loc
                        del new_loc
                    except (ValueError, ImportError):
                        raise DiscoveryError("Failed to find module %s" % locator)
                else:
                    try:
                        test_module = __import__('.'.join(locator.split('.')[:-1]))
                    except (ValueError, ImportError):
                        raise DiscoveryError("Failed to find module %s" % locator)
            except Exception:
                raise DiscoveryError("Got unknown error when trying to import %s:\n\n%s" % (
                    locator,
                    ''.join(traceback.format_exception(*sys.exc_info()))
                ))

            for part in locator.split('.')[1:]:
                try:
                    test_module = getattr(test_module, part)
                except AttributeError:
                    message = "discovery(%s) failed: module %s has no attribute %r" % (locator, test_module, part)
                    if import_error is not None:
                        message += "; this is most likely due to earlier error %r" % (import_error,)
                    raise DiscoveryError(message)
        else:
            test_module = locator

        # if it's a list, iterate it and add its members
        if isinstance(test_module, (list, tuple)):
            for item in test_module:
                for test_case_class in discover_inner(item):
                    yield test_case_class

        # If it's actually a package, recursively descend.  If it's a true module, import its TestCase members
        elif isinstance(test_module, types.ModuleType):
            module_suites = suites + getattr(test_module, '_suites', [])

            # If it has a __path__, it should be a package (directory)
            if hasattr(test_module, '__path__'):
                module_filesystem_path = test_module.__path__[0]
                # but let's be sure
                if os.path.isdir(module_filesystem_path):
                    contents = os.listdir(module_filesystem_path)
                    for item in contents:
                        # ignore .svn and other miscellanea
                        if item.startswith('.'):
                            continue

                        # If it's actually a package (directory + __init__.py)
                        item_path = os.path.join(module_filesystem_path, item)
                        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, '__init__.py')):
                            for test_case_class in discover_inner("%s.%s" % (locator, item), suites=module_suites):
                                yield test_case_class

                        # other than directories, only look in .py files
                        elif item.endswith('.py'):
                            for test_case_class in discover_inner("%s.%s" % (locator, item[:-3]), suites=module_suites):
                                yield test_case_class

            # Otherwise it's some other type of module
            else:
                for member_name in dir(test_module):
                    obj = getattr(test_module, member_name)
                    if isinstance(obj, types.TypeType) and inspect.getmodule(obj) == test_module:
                        for test_case_class in discover_inner(obj, suites=module_suites):
                            yield test_case_class

        # it's not a list, it's not a bare module - let's see if it's an honest-to-god TestCaseBase
        elif isinstance(test_module, MetaTestCase) and (not '__test__' in test_module.__dict__ or bool(test_module.__test__)):
                if test_module not in discover_set:
                    _log.debug("discover: discovered %s" % test_module)
                    if suites:
                        if not hasattr(test_module, '_suites'):
                            setattr(test_module, '_suites', set())
                        elif not isinstance(test_module._suites, set):
                            test_module._suites = set(test_module._suites)
                        test_module._suites = test_module._suites | set(suites)
                    discover_set.add(test_module)
                    yield test_module

        # detect unittest test cases
        elif issubclass(test_module, unittest.TestCase) and (not '__test__' in test_module.__dict__ or bool(test_module.__test__)):
            test_case = TestifiedUnitTest.from_unittest_case(test_module, module_suites=suites)
            discover_set.add(test_case)
            yield test_case

    discover_set = set()
    time_start = time.time()

    for discovery in discover_inner(what):
        yield discovery

    time_end = time.time()
    _log.debug("discover: discovered %d test cases in %s" % (len(discover_set), time_end - time_start))

def import_test_class(module_path, class_name):
    for klass in discover(module_path):
        if klass.__name__ == class_name:
            return klass

    raise DiscoveryError(class_name)
