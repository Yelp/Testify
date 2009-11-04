import logging
import os
import os.path
import time
import types
import sys
from test_case import MetaTestCase
from test_logger import _log

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

    def discover_inner(locator, suites=[]):
        if isinstance(locator, basestring):
            try:
                test_module = __import__(locator)
            except ImportError:
                test_module = __import__('.'.join(locator.split('.')[:-1]))
            
            for part in locator.split('.')[1:]:
                try:
                    test_module = getattr(test_module, part)
                except AttributeError, exc:
                    # The attribute error message isn't helpful at all.
                    message = "discovery(%s) failed: module %s has no attribute %s" % (locator,test_module, part)
                    raise Exception(message)
        else:
            test_module = locator

        # if it's a list, iterate it and add its members
        if isinstance(test_module, (list, tuple)):
            for item in test_module:
                for test_case_class in discover_inner(item):
                    yield test_case_class

        # If it's actually a package, recursively descend.  If it's a true module, import its TestCase members
        elif isinstance(test_module, types.ModuleType):
            # If it has a __path__, it should be a package (directory)
            if hasattr(test_module, '__path__'):
                module_suites = getattr(test_module, '_suites', [])
                module_filesystem_path = test_module.__path__[0]
                # but let's be sure
                if os.path.isdir(module_filesystem_path):
                    contents = os.listdir(module_filesystem_path)
                    for item in contents:
                        # ignore .svn and other miscellanea
                        if not item.startswith('.'):
                            if os.path.isdir(os.path.join(module_filesystem_path, item)):
                                for test_case_class in discover_inner("%s.%s" % (locator, item), suites+module_suites):
                                    yield test_case_class

                            # other than directories, only look in .py files
                            elif item.endswith('.py'):
                                for test_case_class in discover_inner("%s.%s" % (locator, item[:-3]), suites+module_suites):
                                    yield test_case_class

            # Otherwise it's some other type of module
            else:
                module_suites = getattr(test_module, '_suites', [])
                for member_name in dir(test_module):
                    obj = getattr(test_module, member_name)
                    if isinstance(obj, types.TypeType):
                        for test_case_class in discover_inner(obj, suites + module_suites):
                            yield test_case_class

        # it's not a list, it's not a bare module - let's see if it's an honest-to-god TestCaseBase
        else:
            if isinstance(test_module, MetaTestCase) and (not '__test__' in test_module.__dict__ or bool(test_module.__test__)):
                if test_module not in discover_set:
                    _log.debug("discover: discovered %s" % test_module)
                    if suites:
                        if not hasattr(test_module, '_suites'):
                            setattr(test_module, '_suites', set())
                        elif not isinstance(test_module._suites, set):
                            test_module._suites = set(test_module._suites)
                        test_module._suites.update(set(suites))
                    discover_set.add(test_module)
                    yield test_module

    discover_set = set()
    time_start = time.time()
    for discovery in discover_inner(what):
        yield discovery
    time_end = time.time()
    _log.debug("discover: discovered %d test cases in %s" % (len(discover_set), time_end - time_start))
