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

### TODO: finish doing the retry stuff for the inner clauses

__author__ = "Oliver Nicholas <bigo@yelp.com>"
__testify = 1

from collections import defaultdict
import datetime
import inspect
import logging
from new import instancemethod
import sys
import traceback
import types

from test_result import TestResult
import deprecated_assertions
from testify.utils import class_logger

# just a useful list to have
fixture_types = ['class_setup', 'setup', 'teardown', 'class_teardown']
deprecated_fixture_type_map = {
    'classSetUp': 'class_setup', 
    'setUp': 'setup', 
    'tearDown': 'teardown', 
    'classTearDown': 'class_teardown'}

class TwistedFailureError(Exception): 
    """Exception that indicates the value is an instance of twisted.python.failure.Failure
    
    This is part of the magic that's required to get a proper stack trace out of twisted applications
    """
    pass

class MetaTestCase(type):
    """This base metaclass is used to collect each TestCase's decorated fixture methods at
    runtime.  It is implemented as a metaclass so we can determine the order in which 
    fixture methods are defined.
    """
    __test__ = False
    _fixture_accumulator = defaultdict(list)
    def __init__(cls, name, bases, dct):

        for member_name, member in dct.iteritems():
            if member_name.startswith('test') and isinstance(member, types.FunctionType):
                if not hasattr(member, '_suites'):
                    member._suites = set()

        super(MetaTestCase, cls).__init__(name, bases, dct)

        # grab the collected fixtures and then re-init the accumulator
        cls._fixture_methods = MetaTestCase._fixture_accumulator
        MetaTestCase._fixture_accumulator = defaultdict(list)

    @classmethod
    def _cmp_str(cls, instance):
        """Return a canonical representation of a TestCase for sorting and hashing."""
        return "%s.%s" % (instance.__module__, instance.__name__)

    def __cmp__(self, other):
        """Sort TestCases by a particular string representation."""
        return cmp(MetaTestCase._cmp_str(self), MetaTestCase._cmp_str(other))
    
    def bucket(self, bucket_count):
        """Bucket a TestCase using a relatively consistant hash - for dividing tests across runners."""
        return hash(MetaTestCase._cmp_str(self)) % bucket_count

def discovered_test_cases():
    return [test_case_class for test_case_class in MetaTestCase._test_accumulator if test_case_class != TestCase]

class TestCase(object):
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
    __metaclass__ = MetaTestCase
    __test__ = False

    STAGE_CLASS_SETUP = 1
    STAGE_SETUP = 2
    STAGE_TEST_METHOD = 3
    STAGE_TEARDOWN = 4
    STAGE_CLASS_TEARDOWN = 5
    
    log = class_logger.ClassLogger()

    def __init__(self, *args, **kwargs):
        super(TestCase, self).__init__()

        # ascend the class hierarchy and discover fixture methods
        self.__init_fixture_methods()

        self.__suites_include = kwargs.get('suites_include', set())
        self.__suites_exclude = kwargs.get('suites_exclude', set())
        self.__name_overrides = kwargs.get('name_overrides', None)

        # if the class has any suites applied to it, copy them down into its test methods
        if hasattr(self, '_suites'):
            for member_name in dir(self):
                if member_name.startswith('test'):
                    member = getattr(self, member_name)
                    if isinstance(member, types.MethodType):
                        suited_function = suite(*getattr(self, '_suites'))(member)
                        setattr(self, member_name, suited_function)

        # callbacks for various stages of execution, used for stuff like logging
        self.__on_run_test_method_callbacks = []
        self.__on_complete_test_method_callbacks = []
        
        # one of these will later be populated with exception info if there's an
        # exception in the class_setup/class_teardown stage
        self.__class_level_failure = None
        self.__class_level_error = None

        # for now, we still support the use of unittest-style fixture methods
        for deprecated_fixture_type in ['classSetUp', 'setUp', 'tearDown', 'classTearDown']:
            getattr(self, deprecated_fixture_type).im_func._fixture_type = deprecated_fixture_type_map[deprecated_fixture_type]

        # for now, we still support the use of unittest-style assertions defined on the TestCase instance
        for name in dir(deprecated_assertions):
            if name.startswith(('assert', 'fail')):
                setattr(self, name, instancemethod(getattr(deprecated_assertions, name), self, self.__class__))

    def __init_fixture_methods(self):
        """Initialize and populate the lists of fixture methods for this TestCase.
        Fixture methods are added by the MetaTestCase metaclass at runtime only to
        the class on which they are initially defined.  This means in order to figure
        out all the fixtures this particular TestCase will need, we have to ascend
        its class hierarchy and collect all the fixture methods defined on earlier
        classes.
        """
        # init our self.(class_setup|setup|teardown|class_teardown)_fixtures lists
        for fixture_type in fixture_types:
            setattr(self, "%s_fixtures" % fixture_type, [])

        # for setup methods, we want oldest class first.  for teardowns, we want newest class first
        hierarchy = list(reversed(type(self).mro()))
        for cls in hierarchy[1:]:
            # mixins on TestCase instances that derive from, say, object, won't be set up properly
            if hasattr(cls, '_fixture_methods'):
                # the metaclass stored the class's fixtures in a _fixture_methods instance variable
                for fixture_type, fixture_methods in cls._fixture_methods.iteritems():
                    bound_fixture_methods = [instancemethod(func, self, self.__class__) for func in fixture_methods]
                    if fixture_type.endswith('setup'):
                        # for setup methods, we want methods defined further back in the
                        # class hierarchy to execute first
                        getattr(self, "%s_fixtures" % fixture_type).extend(bound_fixture_methods)
                    else:
                        # for teardown methods though, we want the opposite
                        setattr(self, "%s_fixtures" % fixture_type, bound_fixture_methods + getattr(self, "%s_fixtures" % fixture_type))

    def _generate_test_method(self, method_name, function):
        """Allow tests to define new test methods in their __init__'s and have appropriate suites applied."""
        suited_function = suite(*getattr(self, '_suites', set()))(function)
        setattr(self, method_name, instancemethod(function, self, self.__class__))

    def runnable_test_methods(self):
        """Generator method to yield runnable test methods.

        This will pick out the test methods from this TestCase, and then exclude any in
        any of our exclude_suites.  If there are any include_suites, it will then further
        limit itself to test methods in those suites.
        """
        for member_name in dir(self):
            if member_name.startswith("test"):
                member = getattr(self, member_name)
                if inspect.ismethod(member):
                    member_suites = set(getattr(member, '_suites', set()))
                    # if there are any exclude suites, exclude methods under them
                    if (not self.__suites_exclude) or (not self.__suites_exclude & member_suites):
                        # if there are any include suites, only run methods in them
                        if not self.__suites_include or (self.__suites_include & member_suites):
                            # if there are any name overrides, only run the named methods
                            if self.__name_overrides is None or member.__name__ in self.__name_overrides:
                                yield member

    def run(self):
        """Delegator method encapsulating the flow for executing a TestCase instance"""
        self.__run_class_setup_fixtures()
        self.__run_test_methods()
        self.__run_class_teardown_fixtures()

    def __run_class_setup_fixtures(self):
        """Running the class's class_setup method chain."""
        self._stage = self.STAGE_CLASS_SETUP

        for fixture_method in self.class_setup_fixtures:
            result = TestResult(fixture_method)

            try:
                for callback in self.__on_run_test_method_callbacks:
                    callback(self, fixture_method)

                result.start()

                if self.__execute_block_recording_exceptions(fixture_method, result, is_class_level=True):
                    result.end_in_success()
            except (KeyboardInterrupt, SystemExit):
                result.end_in_incomplete(sys.exc_info())
                for callback in self.__on_complete_test_method_callbacks:
                    callback(self, result)
                raise
            else:
                for callback in self.__on_complete_test_method_callbacks:
                    callback(self, result)

        self.__run_deprecated_fixture_method('classSetUp')

    def __run_class_teardown_fixtures(self):
        """End the process of running tests.  Run the class's class_teardown methods"""
        self._stage = self.STAGE_CLASS_TEARDOWN
        
        self.__run_deprecated_fixture_method('classTearDown')

        for fixture_method in self.class_teardown_fixtures:
            result = TestResult(fixture_method)
            try:
                for callback in self.__on_run_test_method_callbacks:
                    callback(self, fixture_method)

                result.start()

                if self.__execute_block_recording_exceptions(fixture_method, result, is_class_level=True):
                    result.end_in_success()
            except (KeyboardInterrupt, SystemExit):
                result.end_in_incomplete(sys.exc_info())
                for callback in self.__on_complete_test_method_callbacks:
                    callback(self, result)
                raise
            else:
                for callback in self.__on_complete_test_method_callbacks:
                    callback(self, result)

    @classmethod
    def in_suite(cls, method, suite_name):
        """Return a bool denoting whether the given method is in the given suite."""
        return suite_name in getattr(method, '_suites', set())

    def method_excluded(self, method):
        """Given this TestCase's included/excluded suites, is this test method excluded?

        Returns a set of the excluded suites that the argument method is in, or an empty
        suite if none.
        """
        method_suites = set(getattr(method, '_suites', set()))
        return (self.__suites_exclude & method_suites)

    def __run_test_methods(self):
        """Run this class's setup fixtures / test methods / teardown fixtures.
        
        These are run in the obvious order - setup and teardown go before and after, 
        respectively, every test method.  If there was a failure in the class_setup
        phase, no method-level fixtures or test methods will be run, and we'll eventually
        skip all the way to the class_teardown phase.   If a given test method is marked
        as disabled, neither it nor its fixtures will be run.  If there is an exception
        during during the setup phase, the test method will not be run and execution
        will continue with the teardown phase.
        """
        for test_method in self.runnable_test_methods():

            result = TestResult(test_method)
            test_method.im_self.test_result = result

            try:
                # run "on-run" callbacks. eg/ print out the test method name
                for callback in self.__on_run_test_method_callbacks:
                    callback(self, test_method)
                result.start()

                if self.__class_level_failure:
                    result.end_in_failure(self.__class_level_failure)
                elif self.__class_level_error:
                    result.end_in_error(self.__class_level_error)
                else:
                    # first, run setup fixtures
                    self._stage = self.STAGE_SETUP
                    def _setup_block():
                        for fixture_method in self.setup_fixtures:
                            fixture_method()
                        self.__run_deprecated_fixture_method('setUp')
                    self.__execute_block_recording_exceptions(_setup_block, result)

                    # then run the test method itself, assuming setup was successful
                    self._stage = self.STAGE_TEST_METHOD
                    if not result.complete:
                        self.__execute_block_recording_exceptions(test_method, result)

                    # finally, run the teardown phase
                    self._stage = self.STAGE_TEARDOWN
                    def _teardown_block():
                        self.__run_deprecated_fixture_method('tearDown')
                        for fixture_method in self.teardown_fixtures:
                            fixture_method()
                    self.__execute_block_recording_exceptions(_teardown_block, result)

                # if nothing's gone wrong, it's not about to start
                if not result.complete:
                    result.end_in_success()
            except (KeyboardInterrupt, SystemExit):
                result.end_in_incomplete(sys.exc_info())
                for callback in self.__on_complete_test_method_callbacks:
                    callback(self, result)
                raise
            else:
                for callback in self.__on_complete_test_method_callbacks:
                    callback(self, result)

    EVENT_ON_RUN_TEST_METHOD = 1
    EVENT_ON_COMPLETE_TEST_METHOD = 2

    def register_callback(self, event, callback):
        """Register a callback for an internal event, usually used for logging.

        The argument to the callback will be the test method object itself.

        Fixture objects can be distinguished by the running them through self.is_fixture_method().
        """
        if event == self.EVENT_ON_RUN_TEST_METHOD:
            self.__on_run_test_method_callbacks.append(callback)
        elif event == self.EVENT_ON_COMPLETE_TEST_METHOD:
            self.__on_complete_test_method_callbacks.append(callback)
        else:
            raise ValueError("Invalid callback event: %s" % event)

    def __execute_block_recording_exceptions(self, block_fxn, result, is_class_level=False):
        """Excerpted code for executing a block of code that might except and cause us to update a result object.
        
        Return value is a boolean describing whether the block was successfully executed without exceptions.
        """
        try:
            block_fxn()
        except (KeyboardInterrupt, SystemExit):
            raise
        except TwistedFailureError, exception:
            # We provide special support for handling the failures that are generated from twisted.
            # Due to complexities in error handling and cleanup, it's difficult to get the raw exception
            # data from an asynchcronous failure, so we really get a pseudo traceback object. 
            failure = exception.args[0]
            exc_info = (failure.type, failure.value, failure.getTracebackObject())
            result.end_in_error(exc_info)
            if is_class_level:
                self.__class_level_failure = exc_info
        except Exception, exception:
            if isinstance(exception, AssertionError):
                result.end_in_failure(sys.exc_info())
                if is_class_level:
                    self.__class_level_failure = sys.exc_info()
            else:
                result.end_in_error(sys.exc_info())
                if is_class_level:
                    self.__class_level_error = sys.exc_info()
            return False
        else:
            return True

    def classSetUp(self): pass
    def setUp(self): pass
    def tearDown(self): pass
    def classTearDown(self): pass

    def is_fixture_method(self, method, fixture_type = None):
        if hasattr(method, '_fixture_type'):
            if fixture_type:
                return True if (getattr(method, '_fixture_type') == fixture_type) else False
            else:
                return True

    def __run_deprecated_fixture_method(self, fixture_name):
        """This runs an old-style (eg/ 'def setUp') fixture method."""
        if hasattr(self, fixture_name):
            deprecated_method = getattr(self, fixture_name)

            if fixture_name.startswith('class'):
                result = TestResult(deprecated_method)
                try:
                    for callback in self.__on_run_test_method_callbacks:
                        callback(self, deprecated_method)

                    result.start()
                    if self.__execute_block_recording_exceptions(deprecated_method, result, is_class_level=True):
                        result.end_in_success()
                except (KeyboardInterrupt, SystemExit):
                    result.end_in_incomplete(sys.exc_info())
                    for callback in self.__on_complete_test_method_callbacks:
                        callback(self, result)
                    raise
                else:
                    for callback in self.__on_complete_test_method_callbacks:
                        callback(self, result)
            else:
                deprecated_method()

def suite(*args, **kwargs):
    """Decorator to conditionally assign suites to individual test methods.

    This decorator takes a variable number of positional suite arguments and two optional kwargs:
        - conditional: if provided and does not evaluate to True, the suite will not be applied.
        - reason: if provided, will be attached to the method for logging later.

    Can be called multiple times on one method to assign individual conditions or reasons.
    """
    def mark_test_with_suites(function):
        conditions = kwargs.get('conditions')
        reason = kwargs.get('reason')
        if not hasattr(function, '_suites'):
            function._suites = set()
        if args and (conditions is None or bool(conditions) is True):
            function._suites.update(set(args))
            if reason:
                if not hasattr(function, '_suite_reasons'):
                    function._suite_reasons = []
                function._suite_reasons.append(reason)
        return function

    return mark_test_with_suites

def __fixture_decorator_factory(fixture_type):
    """Decorator generator for the fixture decorators"""
    def fixture_method(func):
        MetaTestCase._fixture_accumulator[fixture_type].append(func)
        func._fixture_type = fixture_type
        return func
    return fixture_method

class_setup = __fixture_decorator_factory('class_setup')
setup = __fixture_decorator_factory('setup')
teardown = __fixture_decorator_factory('teardown')
class_teardown = __fixture_decorator_factory('class_teardown')
