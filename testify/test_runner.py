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

from __future__ import print_function

"""This module contains the TestRunner class and other helper code"""
__author__ = "Oliver Nicholas <bigo@yelp.com>"
__testify = 1

from collections import defaultdict
import itertools
import functools
import pprint
import sys

from test_case import MetaTestCase, TestCase
import test_discovery


class TestRunner(object):
    """TestRunner is the controller class of the testify suite.

    It is responsible for collecting a list of TestCase subclasses, instantiating and
    running them, delegating the collection of results and printing of statistics.
    """

    def __init__(self,
                 test_path_or_test_case,
                 bucket=None,
                 bucket_count=None,
                 bucket_overrides=None,
                 bucket_salt=None,
                 debugger=None,
                 suites_include=(),
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
        self.bucket = bucket
        self.bucket_count = bucket_count
        self.bucket_overrides = bucket_overrides if bucket_overrides is not None else {}
        self.bucket_salt = bucket_salt

        self.debugger = debugger

        self.suites_include = set(suites_include)
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
        return '%s %s.%s' % (
            test_method.im_class.__module__,
            test_method.im_class.__name__,
            test_method.__name__,
        )

    def discover(self):
        def construct_test(test_case_class):
            test_case = test_case_class(
                suites_include=self.suites_include,
                suites_exclude=self.suites_exclude,
                suites_require=self.suites_require,
                name_overrides=self.module_method_overrides.get(test_case_class.__name__, None),
                failure_limit=(self.failure_limit - self.failure_count) if self.failure_limit else None,
                debugger=self.debugger,
            )
            return test_case

        def discover_tests():
            return [
                construct_test(test_case_class)
                for test_case_class in test_discovery.discover(self.test_path_or_test_case)
                if not self.module_method_overrides or test_case_class.__name__ in self.module_method_overrides
            ]

        def discover_tests_by_buckets():
            # Sort by the test count, use the cmp_str as a fallback for determinism
            test_cases = sorted(
                discover_tests(),
                key=lambda test_case: (
                    -1 * len(list(test_case.runnable_test_methods())),
                    MetaTestCase._cmp_str(type(test_case)),
                )
            )

            # Assign buckets round robin
            buckets = defaultdict(list)
            for bucket, test_case in itertools.izip(
                itertools.cycle(
                    range(self.bucket_count) + list(reversed(range(self.bucket_count)))
                ),
                test_cases,
            ):
                # If the class is supposed to be specially bucketed, do so
                bucket = self.bucket_overrides.get(MetaTestCase._cmp_str(type(test_case)), bucket)
                buckets[bucket].append(test_case)

            return buckets[self.bucket]

        def discover_tests_testing():
            # For testing purposes only
            return [self.test_path_or_test_case()]

        discovered_tests = []
        try:
            if isinstance(self.test_path_or_test_case, (TestCase, MetaTestCase)):
                discovered_tests = discover_tests_testing()
            elif self.bucket is not None:
                discovered_tests = discover_tests_by_buckets()
            else:
                discovered_tests = discover_tests()
        except test_discovery.DiscoveryError, exc:
            for reporter in self.test_reporters:
                reporter.test_discovery_failure(exc)
            sys.exit(1)
        test_case_count = len(discovered_tests)
        test_method_count = sum(len(list(test_case.runnable_test_methods())) for test_case in discovered_tests)
        for reporter in self.test_reporters:
            reporter.test_counts(test_case_count, test_method_count)
        return discovered_tests

    def run(self):
        """Instantiate our found test case classes and run their test methods.

        We use this opportunity to apply any test method name overrides that were parsed
        from the command line (or rather, passed in on initialization).

        Logging of individual results is accomplished by registering callbacks for
        the TestCase instances to call when they begin and finish running each test.

        At its conclusion, we pass our collected results to our TestLogger to
        print out exceptions and testing summaries.
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
                    test_case.register_callback(test_case.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD, reporter.class_teardown_complete)

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

        except (KeyboardInterrupt, SystemExit):
            # we'll catch and pass a keyboard interrupt so we can cancel in the middle of a run
            # but still get a testing summary.
            pass

        report = [reporter.report() for reporter in self.test_reporters]
        return all(report)

    def list_suites(self):
        """List the suites represented by this TestRunner's tests."""
        suites = defaultdict(list)
        for test_instance in self.discover():
            for test_method in test_instance.runnable_test_methods():
                for suite_name in test_instance.suites(test_method):
                    suites[suite_name].append(test_method)
        suite_counts = dict((suite_name, "%d tests" % len(suite_members)) for suite_name, suite_members in suites.iteritems())

        pp = pprint.PrettyPrinter(indent=2)
        print(pp.pformat(dict(suite_counts)))

        return suite_counts

    def get_tests_for_suite(self, selected_suite_name):
        """Gets the test list for the suite"""
        test_list = []
        for test_instance in self.discover():
            for test_method in test_instance.runnable_test_methods():
                if not selected_suite_name or TestCase.in_suite(test_method, selected_suite_name):
                    test_list.append(test_method)
        return test_list

    def list_tests(self, selected_suite_name=None):
        """Lists all tests, optionally scoped to a single suite."""
        test_list = self.get_tests_for_suite(selected_suite_name)
        for test_method_name in (
            self.get_test_method_name(test)
            for test in test_list
        ):
            print(test_method_name)

        return test_list

# vim: set ts=4 sts=4 sw=4 et:
