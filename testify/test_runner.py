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

"""This module contains the TestRunner class and other helper code"""

from __future__ import absolute_import
from __future__ import print_function

from collections import defaultdict
import functools
import json

import six

from .test_case import MetaTestCase, TestCase
from . import test_discovery
from . import exit
from . import exceptions


__author__ = "Oliver Nicholas <bigo@yelp.com>"
__testify = 1


class TestRunner(object):
    """TestRunner is the controller class of the testify suite.

    It is responsible for collecting a list of TestCase subclasses, instantiating and
    running them, delegating the collection of results and printing of statistics.
    """

    def __init__(self,
                 test_path_or_test_case,
                 debugger=None,
                 suites_exclude=(),
                 suites_require=(),
                 options=None,
                 test_reporters=None,
                 plugin_modules=None,
                 module_method_overrides=None,
                 failure_limit=None
                 ):
        """After instantiating a TestRunner, call run() to run them."""

        self.test_path_or_test_case = test_path_or_test_case

        self.debugger = debugger

        self.suites_exclude = set(suites_exclude)
        self.suites_require = set(suites_require)

        self.options = options

        self.plugin_modules = plugin_modules or []
        self.test_reporters = test_reporters or []
        self.module_method_overrides = module_method_overrides if module_method_overrides is not None else {}

        self.failure_limit = failure_limit
        self.failure_count = 0

    @classmethod
    def get_test_method_name(cls, test_method):
        test_method_self_t = type(six.get_method_self(test_method))
        # PY2, unbound methods hit this
        # PY3 you get attributeerror on __self__ one line above
        assert not isinstance(test_method_self_t, type(None))
        return '%s %s.%s' % (
            test_method_self_t.__module__,
            test_method_self_t.__name__,
            test_method.__name__,
        )

    def _construct_test(self, test_case_cls, **kwargs):
        name_overrides = kwargs.pop(
            'name_overrides',
            self.module_method_overrides.get(test_case_cls.__name__, None),
        )
        test_case = test_case_cls(
            suites_exclude=self.suites_exclude,
            suites_require=self.suites_require,
            name_overrides=name_overrides,
            failure_limit=(self.failure_limit - self.failure_count) if self.failure_limit else None,
            debugger=self.debugger,
            **kwargs
        )

        # Add in information from plugins
        for plugin_mod in self.plugin_modules:
            if hasattr(plugin_mod, 'add_testcase_info'):
                plugin_mod.add_testcase_info(test_case, self)

        return test_case

    def discover(self):
        if isinstance(self.test_path_or_test_case, (TestCase, MetaTestCase)):
            # For testing purposes only
            return [self.test_path_or_test_case()]
        else:
            return (
                self._construct_test(test_case_class)
                for test_case_class in test_discovery.discover(self.test_path_or_test_case)
                if not self.module_method_overrides or test_case_class.__name__ in self.module_method_overrides
            )

    def run(self):
        """Instantiate our found test case classes and run their test methods.

        We use this opportunity to apply any test method name overrides that were parsed
        from the command line (or rather, passed in on initialization).

        Logging of individual results is accomplished by registering callbacks for
        the TestCase instances to call when they begin and finish running each test.

        At its conclusion, we pass our collected results to our TestLogger to
        print out exceptions and testing summaries.

        Returns an exit code from sysexits.h. See:
            http://linux.die.net/include/sysexits.h
        """

        try:
            for test_case in self.discover():
                if self.failure_limit and self.failure_count >= self.failure_limit:
                    break

                # We allow our plugins to mutate the test case prior to execution
                for plugin_mod in self.plugin_modules:
                    if hasattr(plugin_mod, "prepare_test_case"):
                        plugin_mod.prepare_test_case(self.options, test_case)

                if not any(test_case.runnable_test_methods()):
                    continue

                def failure_counter(result_dict):
                    if not result_dict['success']:
                        self.failure_count += 1

                for reporter in self.test_reporters:
                    test_case.register_callback(test_case.EVENT_ON_RUN_TEST_METHOD, reporter.test_start)
                    test_case.register_callback(test_case.EVENT_ON_COMPLETE_TEST_METHOD, reporter.test_complete)

                    test_case.register_callback(test_case.EVENT_ON_RUN_CLASS_SETUP_METHOD, reporter.class_setup_start)
                    test_case.register_callback(test_case.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, reporter.class_setup_complete)

                    test_case.register_callback(test_case.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD, reporter.class_teardown_start)
                    test_case.register_callback(
                        test_case.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD,
                        reporter.class_teardown_complete,
                    )

                    test_case.register_callback(test_case.EVENT_ON_RUN_TEST_CASE, reporter.test_case_start)
                    test_case.register_callback(test_case.EVENT_ON_COMPLETE_TEST_CASE, reporter.test_case_complete)

                test_case.register_callback(test_case.EVENT_ON_COMPLETE_TEST_METHOD, failure_counter)

                # Now we wrap our test case like an onion. Each plugin given the opportunity to wrap it.
                runnable = test_case.run
                for plugin_mod in self.plugin_modules:
                    if hasattr(plugin_mod, "run_test_case"):
                        runnable = functools.partial(plugin_mod.run_test_case, self.options, test_case, runnable)

                # And we finally execute our finely wrapped test case
                runnable()

        except exceptions.DiscoveryError as exc:
            for reporter in self.test_reporters:
                reporter.test_discovery_failure(exc)
            return exit.DISCOVERY_FAILED
        except exceptions.Interruption:
            # handle interruption so we can cancel in the middle of a run
            # but still get a testing summary.
            pass

        report = [reporter.report() for reporter in self.test_reporters]
        if all(report):
            return exit.OK
        else:
            return exit.TESTS_FAILED

    def list_suites(self):
        """List the suites represented by this TestRunner's tests."""
        suites = defaultdict(list)
        for test_instance in self.discover():
            for test_method in test_instance.runnable_test_methods():
                for suite_name in test_instance.suites(test_method):
                    suites[suite_name].append(test_method)
        return {suite_name: "%d tests" % len(suite_members) for suite_name, suite_members in suites.items()}

    def get_tests_for_suite(self, selected_suite_name):
        """Gets the test list for the suite"""
        for test_instance in self.discover():
            for test_method in test_instance.runnable_test_methods():
                if not selected_suite_name or TestCase.in_suite(test_method, selected_suite_name):
                    yield test_method

    def list_tests(self, format, selected_suite_name=None):
        """Lists all tests, optionally scoped to a single suite."""
        for test in self.get_tests_for_suite(selected_suite_name):
            name = self.get_test_method_name(test)
            if format == 'txt':
                print(name)
            elif format == 'json':
                testcase = test.__self__
                print(json.dumps(
                    dict(
                        test=name,
                        suites=sorted(testcase.suites(test)),
                    ),
                    sort_keys=True,
                ))
            else:
                raise ValueError("unknown test list format: '%s'" % format)

# vim: set ts=4 sts=4 sw=4 et:
