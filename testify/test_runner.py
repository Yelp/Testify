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
__author__ = "Oliver Nicholas <bigo@yelp.com>"
__testify = 1

from collections import defaultdict
import datetime
import logging
from optparse import OptionParser
import os
import pprint
import sys
import traceback
import types

import code_coverage
from test_case import MetaTestCase, TestCase
import test_discovery
from test_logger import _log, TextTestLogger, VERBOSITY_SILENT, VERBOSITY_NORMAL, VERBOSITY_VERBOSE

class TestRunner(object):
    """TestRunner is the controller class of the testify suite.  

    It is responsible for collecting a list of TestCase subclasses, instantiating and 
    running them, delegating the collection of results and printing of statistics.
    """

    def __init__(self,
        verbosity=VERBOSITY_NORMAL,
        suites_include=[],
        suites_exclude=[],
        coverage=False,
        summary_mode=False,
        test_logger_class=TextTestLogger,
        module_method_overrides={}):
        """After instantiating a TestRunner, call add_test_case() to add some tests, and run() to run them."""
        self.verbosity = verbosity

        self.suites_include = set(suites_include)
        self.suites_exclude = set(suites_exclude)

        self.coverage = coverage
        self.logger = test_logger_class(self.verbosity)
        self.summary_mode = summary_mode

        self.module_method_overrides = module_method_overrides
        self.test_case_classes = []

    @classmethod
    def get_test_method_name(cls, test_method):
        return '%s %s.%s' % (test_method.__module__, test_method.im_class.__name__, test_method.__name__)

    def discover(self, test_path, bucket=None, bucket_count=None, bucket_overrides={}):
        for test_case_class in test_discovery.discover(test_path):
            override_bucket = bucket_overrides.get(MetaTestCase._cmp_str(test_case_class))
            if (bucket is None
                or (override_bucket is None and test_case_class.bucket(bucket_count) == bucket)
                or (override_bucket is not None and override_bucket == bucket)):
                if not self.module_method_overrides or test_case_class.__name__ in self.module_method_overrides:
                    self.add_test_case(test_case_class)

    def add_test_case(self, module):
        self.test_case_classes.append(module)

    def run(self):
        """Instantiate our found test case classes and run their test methods.

        We use this opportunity to apply any test method name overrides that were parsed
        from the command line (or rather, passed in on initialization).
        
        Logging of individual results is accomplished by registering callbacks for 
        the TestCase instances to call when they begin and finish running each test.
        
        At its conclusion, we pass our collected results and to our TestLogger to get
        testing exceptions and summaries printed out.
        """

        results = []
        try:
            for test_case_class in self.test_case_classes:
                name_overrides = self.module_method_overrides.setdefault(test_case_class.__name__, None)
                test_case = test_case_class(
                    suites_include=self.suites_include,
                    suites_exclude=self.suites_exclude,
                    name_overrides=name_overrides)
                if not any(test_case.runnable_test_methods()):
                    continue

                # the TestCase on_run_test_method callback calls its registrants with
                # the test method as the argument.
                def _log_real_test_method_names(test_method):
                    """Log the names of test methods before they are executed"""
                    if not test_case.is_fixture_method(test_method) and not test_case.method_excluded(test_method):
                        self.logger.report_test_name(test_method)

                test_case.register_callback(test_case.EVENT_ON_RUN_TEST_METHOD, _log_real_test_method_names)

                # The TestCase on_complete_test_method callback calls its registrants
                # with the result object as the argument.
                def _append_relevant_results_and_log_relevant_failures(result):
                    """Log the results of test methods."""
                    if not test_case.is_fixture_method(result.test_method):
                        if not test_case.method_excluded(result.test_method):
                            self.logger.report_test_result(result)
                        results.append(result)
                    elif result.test_method._fixture_type == 'class_teardown' and (result.failure or result.error):
                        # For a class_teardown failure, log the name too (since it wouldn't have 
                        # already been logged by on_run_test_method).
                        self.logger.report_test_name(result.test_method)
                        self.logger.report_test_result(result)
                        results.append(result)
                    if not result.success and not result.skipped and not TestCase.in_suite(result.test_method, 'expected-failure'):
                        self.logger.failure(result)

                test_case.register_callback(test_case.EVENT_ON_COMPLETE_TEST_METHOD, _append_relevant_results_and_log_relevant_failures)

                # Now that we are going to run the actually test case, start tracking coverage if requested.
                if self.coverage:
                    code_coverage.start(test_case.__class__.__module__ + "." + test_case.__class__.__name__)
                    
                # callbacks registered, this will actually run the TestCase's fixture and test methods
                test_case.run()
                
                # Stop tracking and save the coverage info
                if self.coverage:
                    code_coverage.stop()

        except (KeyboardInterrupt, SystemExit), e:
            # we'll catch and pass a keyboard interrupt so we can cancel in the middle of a run
            # but still get a testing summary.
            pass

        # All the TestCases have been run - now collate results by status and log them
        results_by_status = defaultdict(list)
        for result in results:
            if result.success:
                if result.unexpected_success:
                    results_by_status['unexpected_success'].append(result)
                else:
                    results_by_status['successful'].append(result)
            elif result.failure or result.error:
                results_by_status['failed'].append(result)
            elif result.skipped:
                results_by_status['skipped'].append(result)
            elif result.incomplete:
                results_by_status['incomplete'].append(result)
            else:
                results_by_status['unknown'].append(result)

        if self.summary_mode:
            self.logger.report_failures(results_by_status['failed'])
        # if results_by_status['skipped']:
        #   self.logger.report_skippeds(results_by_status['skipped'])
        self.logger.report_stats(len(self.test_case_classes), **results_by_status)

        return bool((len(results_by_status['failed']) + len(results_by_status['unknown'])) == 0)
    
    def list_suites(self):
        """List the suites represented by this TestRunner's tests."""
        suites = defaultdict(list)
        for test_case_class in self.test_case_classes:
            test_instance = test_case_class(
                suites_include=self.suites_include,
                suites_exclude=self.suites_exclude)
            for test_method in test_instance.runnable_test_methods():
                for suite_name in test_method._suites:
                    suites[suite_name].append(test_method)
        suite_counts = dict((suite_name, "%d tests" % len(suite_members)) for suite_name, suite_members in suites.iteritems())

        pp = pprint.PrettyPrinter(indent=2)
        print(pp.pformat(dict(suite_counts)))

    def list_tests(self, selected_suite_name=None):
        """Lists all tests, optionally scoped to a single suite."""
        test_list = []
        for test_case_class in self.test_case_classes:
            test_instance = test_case_class(
                suites_include=self.suites_include,
                suites_exclude=self.suites_exclude)
            for test_method in test_instance.runnable_test_methods():
                if not selected_suite_name or TestCase.in_suite(test_method, selected_suite_name):
                    test_list.append(test_method)

        pp = pprint.PrettyPrinter(indent=2)
        print(pp.pformat([self.get_test_method_name(test) for test in test_list]))
