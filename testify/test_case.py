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


"""This module contains the TestCase class and other helper code, like decorators for test methods."""

from __future__ import absolute_import

from collections import defaultdict
import functools
import inspect
import types
import unittest

import six

from testify import test_fixtures
from testify.exceptions import Interruption
from testify.utils import class_logger
from testify.test_fixtures import DEPRECATED_FIXTURE_TYPE_MAP
from testify.test_fixtures import TestFixtures
from testify.test_fixtures import suite
from .test_result import TestResult
from . import deprecated_assertions


__author__ = "Oliver Nicholas <bigo@yelp.com>"
__testify = 1


class MetaTestCase(type):
    """This base metaclass is used to collect each TestCase's decorated fixture methods at
    runtime. It is implemented as a metaclass so we can determine the order in which
    fixture methods are defined.
    """
    __test__ = False

    def __new__(mcls, name, bases, dct):
        # This is the constructor for all TestCase *classes*.
        for member_name, member in dct.items():
            if member_name.startswith('test') and isinstance(member, types.FunctionType):
                if not hasattr(member, '_suites'):
                    member._suites = set()

        # Unfortunately, this implementation detail has become a public interface.
        # The set of suites must include the suites from all bases classes.
        cls_suites = dct.pop('_suites', ())
        bases_suites = [
            getattr(base, '_suites', ())
            for base in bases
        ]
        dct['_suites'] = set().union(cls_suites, *bases_suites)

        return super(MetaTestCase, mcls).__new__(mcls, name, bases, dct)

    @staticmethod
    def _cmp_str(instance):
        """Return a canonical representation of a TestCase for sorting and hashing."""
        return "%s.%s" % (instance.__module__, instance.__name__)


class TestCase(six.with_metaclass(MetaTestCase, object)):
    """The TestCase class defines test methods and fixture methods; it is the meat and potatoes of testing.

    QuickStart:
        define a test method, instantiate an instance and call test_case.run()

    Extended information:
        TestCases can contain any number of test methods, as well as class-level
        setup/teardown methods and setup/teardowns to be wrapped around each test
        method. These are defined by decorators.

        The phases of execution are thus:
        class_setup
            setup
                test_method_1
            teardown
            setup
                test_method_2
            teardown
        class_teardown

        The results of test methods are stored in TestResult objects.

        Additional behavior beyond running tests, such as logging results, is achieved
        by registered callbacks.  For more information see the docstrings for:
            register_on_complete_test_method_callback
            register_on_run_test_method_callback
    """
    __test__ = False

    STAGE_UNSTARTED = 0
    STAGE_CLASS_SETUP = 1
    STAGE_SETUP = 2
    STAGE_TEST_METHOD = 3
    STAGE_TEARDOWN = 4
    STAGE_CLASS_TEARDOWN = 5

    EVENT_ON_RUN_TEST_METHOD = 1
    EVENT_ON_COMPLETE_TEST_METHOD = 2
    EVENT_ON_RUN_CLASS_SETUP_METHOD = 3
    EVENT_ON_COMPLETE_CLASS_SETUP_METHOD = 4
    EVENT_ON_RUN_CLASS_TEARDOWN_METHOD = 5
    EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD = 6
    EVENT_ON_RUN_TEST_CASE = 7
    EVENT_ON_COMPLETE_TEST_CASE = 8

    log = class_logger.ClassLogger()

    # For now, we still support the use of unittest-style assertions defined on
    # the TestCase instance
    for _name in dir(deprecated_assertions):
        if _name.startswith(('assert', 'fail')):
            locals()[_name] = classmethod(
                getattr(deprecated_assertions, _name))
    del _name

    def __init__(self, *args, **kwargs):
        super(TestCase, self).__init__()

        self.__test_fixtures = TestFixtures.discover_from(self)

        self.__suites_exclude = kwargs.get('suites_exclude', set())
        self.__suites_require = kwargs.get('suites_require', set())
        self.__name_overrides = kwargs.get('name_overrides', None)

        TestResult.debug = kwargs.get('debugger')  # sorry :(

        # callbacks for various stages of execution, used for stuff like logging
        self.__callbacks = defaultdict(list)

        self.__all_test_results = []

        self._stage = self.STAGE_UNSTARTED

        self.failure_limit = kwargs.pop('failure_limit', None)
        self.failure_count = 0

    @property
    def test_result(self):
        return self.__all_test_results[-1] if self.__all_test_results else None

    def _generate_test_method(self, method_name, function):
        """Allow tests to define new test methods in their __init__'s and have appropriate suites applied."""
        suite(*getattr(self, '_suites', set()))(function)
        setattr(
            self,
            method_name,
            # http://stackoverflow.com/q/4364565
            function.__get__(self, type(self)),
        )

    def runnable_test_methods(self):
        """Generator method to yield runnable test methods.

        This will pick out the test methods from this TestCase, and then exclude any in
        any of our exclude_suites.  If there are any require_suites, it will then further
        limit itself to test methods in those suites.
        """
        for member_name in dir(self):
            if not member_name.startswith("test"):
                continue
            member = getattr(self, member_name)
            if not inspect.ismethod(member):
                continue

            member_suites = self.suites(member)

            # if there are any exclude suites, exclude methods under them
            if self.__suites_exclude and self.__suites_exclude & member_suites:
                continue
            # if there are any require suites, only run methods in *all* of those suites
            if self.__suites_require and not ((self.__suites_require & member_suites) == self.__suites_require):
                continue

            # if there are any name overrides, only run the named methods
            if self.__name_overrides is None or member.__name__ in self.__name_overrides:
                yield member

    def run(self):
        """Delegator method encapsulating the flow for executing a TestCase instance.
        """
        # The TestResult constructor wants an actual method, which it inspects
        # to determine the method name (and class name, so it must be a method
        # and not a function!). self.run is as good a method as any.
        test_case_result = TestResult(self.run)
        test_case_result.start()
        self.fire_event(self.EVENT_ON_RUN_TEST_CASE, test_case_result)
        self._stage = self.STAGE_CLASS_SETUP
        with self.__test_fixtures.class_context(
                setup_callbacks=[
                    functools.partial(self.fire_event, self.EVENT_ON_RUN_CLASS_SETUP_METHOD),
                    functools.partial(self.fire_event, self.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD),
                ],
                teardown_callbacks=[
                    functools.partial(self.fire_event, self.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD),
                    functools.partial(self.fire_event, self.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD),
                ],
        ) as class_fixture_failures:
            # if we have class fixture failures, we're not going to bother
            # running tests, but we need to generate bogus results for them all
            # and mark them as failed.
            self.__run_test_methods(class_fixture_failures)
            self._stage = self.STAGE_CLASS_TEARDOWN

        # class fixture failures count towards our total
        self.failure_count += len(class_fixture_failures)
        # Once a test case completes we should trigger
        # EVENT_ON_COMPLETE_TEST_CASE event so that we can log/report test case
        # results.

        if not test_case_result.complete:
            test_case_result.end_in_success()
        self.fire_event(self.EVENT_ON_COMPLETE_TEST_CASE, test_case_result)

    @classmethod
    def in_suite(cls, method, suite_name):
        """Return a bool denoting whether the given method is in the given suite."""
        return suite_name in getattr(method, '_suites', set())

    def suites(self, method=None):
        """Returns the suites associated with this test case and, optionally, the given method."""
        suites = set(getattr(self, '_suites', []))
        if method is not None:
            suites |= getattr(method, '_suites', set())
        return suites

    def results(self):
        """Available after calling `self.run()`."""
        if self._stage != self.STAGE_CLASS_TEARDOWN:
            raise RuntimeError('results() called before tests have executed')
        return list(self.__all_test_results)

    def method_excluded(self, method):
        """Given this TestCase's included/excluded suites, is this test method excluded?

        Returns a set of the excluded suites that the argument method is in, or an empty
        suite if none.
        """
        method_suites = set(getattr(method, '_suites', set()))
        return (self.__suites_exclude & method_suites)

    def __run_test_methods(self, class_fixture_failures):
        """Run this class's setup fixtures / test methods / teardown fixtures.

        These are run in the obvious order - setup and teardown go before and after,
        respectively, every test method.  If there was a failure in the class_setup
        phase, no method-level fixtures or test methods will be run, and we'll eventually
        skip all the way to the class_teardown phase.   If a given test method is marked
        as disabled, neither it nor its fixtures will be run.  If there is an exception
        during the setup phase, the test method will not be run and execution
        will continue with the teardown phase.
        """
        for test_method in self.runnable_test_methods():
            result = TestResult(test_method)

            # Sometimes, test cases want to take further action based on
            # results, e.g. further clean-up or reporting if a test method
            # fails. (Yelp's Selenium test cases do this.) If you need to
            # programatically inspect test results, you should use
            # self.results().

            # NOTE: THIS IS INCORRECT -- im_self is shared among all test
            # methods on the TestCase instance. This is preserved for backwards
            # compatibility and should be removed eventually.

            try:
                # run "on-run" callbacks. e.g. print out the test method name
                self.fire_event(self.EVENT_ON_RUN_TEST_METHOD, result)

                result.start()
                self.__all_test_results.append(result)

                # if class setup failed, this test has already failed.
                self._stage = self.STAGE_CLASS_SETUP
                for exc_info in class_fixture_failures:
                    result.end_in_failure(exc_info)

                if result.complete:
                    continue

                # first, run setup fixtures
                self._stage = self.STAGE_SETUP
                with self.__test_fixtures.instance_context() as fixture_failures:
                    # we haven't had any problems in class/instance setup, onward!
                    if not fixture_failures:
                        self._stage = self.STAGE_TEST_METHOD
                        result.record(test_method)
                    self._stage = self.STAGE_TEARDOWN

                # maybe something broke during teardown -- record it
                for exc_info in fixture_failures:
                    result.end_in_failure(exc_info)

                if result.interrupted:
                    raise Interruption

                # if nothing's gone wrong, it's not about to start
                if not result.complete:
                    result.end_in_success()

            finally:
                self.fire_event(self.EVENT_ON_COMPLETE_TEST_METHOD, result)

                if not result.success:
                    self.failure_count += 1
                    if self.failure_limit and self.failure_count >= self.failure_limit:
                        break

    def addfinalizer(self, teardown_func):
        if self._stage in (self.STAGE_SETUP, self.STAGE_TEST_METHOD, self.STAGE_TEARDOWN):
            self.__extra_test_teardowns.append(teardown_func)
        elif self._stage in (self.STAGE_CLASS_SETUP, self.STAGE_CLASS_TEARDOWN):
            self.__extra_class_teardowns.append(teardown_func)
        else:
            raise RuntimeError('Tried to add a teardown while the test was not being executed.')

    @test_fixtures.class_setup_teardown
    def __setup_extra_class_teardowns(self):
        self.__extra_class_teardowns = []

        yield

        for teardown in reversed(self.__extra_class_teardowns):
            teardown()

    @test_fixtures.setup_teardown
    def __setup_extra_test_teardowns(self):
        self.__extra_test_teardowns = []

        yield

        for teardown in reversed(self.__extra_test_teardowns):
            teardown()

    def register_callback(self, event, callback):
        """Register a callback for an internal event, usually used for logging.

        The argument to the callback will be the test method object itself.

        Fixture objects can be distinguished by the running them through
        inspection.is_fixture_method().
        """
        self.__callbacks[event].append(callback)

    def fire_event(self, event, result):
        for callback in self.__callbacks[event]:
            callback(result.to_dict())

    def classSetUp(self):
        pass

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def classTearDown(self):
        pass

    def runTest(self):
        pass


class TestifiedUnitTest(TestCase, unittest.TestCase):

    @classmethod
    def from_unittest_case(cls, unittest_class, module_suites=None):
        """"Constructs a new testify.TestCase from a unittest.TestCase class.

        This operates recursively on the TestCase's class hierarchy by
        converting each parent unittest.TestCase into a TestifiedTestCase.

        If 'suites' are provided, they are treated as module-level suites to be
        applied in addition to class- and test-level suites.
        """

        # our base case: once we get to the parent TestCase, replace it with our
        # own parent class that will just handle inheritance for super()
        if unittest_class == unittest.TestCase:
            return TestifiedUnitTest

        # we're going to update our class dict with some testify defaults to
        # make things Just Work
        unittest_dict = dict(unittest_class.__dict__)
        default_test_case_dict = dict(TestCase.__dict__)

        # testify.TestCase defines its own deprecated fixtures; don't let them
        # overwrite unittest's fixtures
        for deprecated_fixture_name in DEPRECATED_FIXTURE_TYPE_MAP:
            del default_test_case_dict[deprecated_fixture_name]

        # set testify defaults on the unittest class
        for member_name, member in default_test_case_dict.items():
            unittest_dict.setdefault(member_name, member)

        # use an __init__ smart enough to figure out our inheritance
        unittest_dict['__init__'] = cls.__init__

        # add module-level suites in addition to any suites already on the class
        class_suites = set(getattr(unittest_class, '_suites', []))
        unittest_dict['_suites'] = class_suites | set(module_suites or [])

        # traverse our class hierarchy and 'testify' parent unittest.TestCases
        bases = []

        for base_class in unittest_class.__bases__:
            if issubclass(base_class, unittest.TestCase):
                base_class = cls.from_unittest_case(base_class, module_suites=module_suites)
            bases.append(base_class)

        # include our original unittest class so existing super() calls still
        # work; this is our last base class to prevent infinite recursion in
        # those super calls
        bases.insert(1, unittest_class)

        new_name = 'Testified' + unittest_class.__name__

        return MetaTestCase(new_name, tuple(bases), unittest_dict)


# vim: set ts=4 sts=4 sw=4 et:
