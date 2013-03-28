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

# TODO: finish doing the retry stuff for the inner clauses

from __future__ import with_statement

__author__ = "Oliver Nicholas <bigo@yelp.com>"
__testify = 1

from collections import defaultdict
from contextlib import contextmanager
import inspect
from new import instancemethod
import sys
import types
import unittest

from test_result import TestResult
import deprecated_assertions
from testify.utils import class_logger
from testify.utils import inspection

FIXTURE_TYPES = (
    'class_setup',
    'setup',
    'teardown',
    'class_teardown',
    'setup_teardown',
    'class_setup_teardown',
)
FIXTURES_WHICH_CAN_RETURN_UNEXPECTED_RESULTS = (
    'class_teardown',
    'class_setup_teardown',
)

# In general, inherited fixtures are applied first unless they are of these
# types. These fixtures are applied (in order of their definitions) starting
# with those defined on the current class, and then those defined on inherited
# classes (following MRO).
REVERSED_FIXTURE_TYPES = (
    'teardown',
    'class_teardown',
)

DEPRECATED_FIXTURE_TYPE_MAP = {
    'classSetUp': 'class_setup',
    'setUp': 'setup',
    'tearDown': 'teardown',
    'classTearDown': 'class_teardown',
}


def make_sortable_fixture_key(fixture):
    """Use class depth, fixture type and fixture id to define
    a sortable key for fixtures.

    Class depth is the most significant value and defines the
    MRO (reverse mro for teardown methods) order. Fixture type
    and fixture id help us to define the expected order.

    See
    test.test_case_test.FixtureMethodRegistrationOrderWithBaseClassTest
    for the expected order.
    """
    if fixture._fixture_type == 'class_setup':
        fixture_order = {
            'class_setup' : 0,
            'class_setup_teardown': 1,
            'class_teardown': 2,
         }
    else:
        fixture_order = {
            'class_setup' : 0,
            'class_setup_teardown': 2,
            'class_teardown': 1,
         }
        if fixture._fixture_type == "class_teardown":
            # class_teardown fixtures should be run in reverse
            # definition order (last definition runs
            # first). Converting fixture_id to its negative
            # value will sort class_teardown fixtures in the
            # same class in reversed order.
            return (fixture._defining_class_depth, fixture_order[fixture._fixture_type], -fixture._fixture_id)

    return (fixture._defining_class_depth, fixture_order[fixture._fixture_type], fixture._fixture_id)


class TwistedFailureError(Exception):
    """Exception that indicates the value is an instance of twisted.python.failure.Failure

    This is part of the magic that's required to get a proper stack trace out of twisted applications
    """
    pass


class MetaTestCase(type):
    """This base metaclass is used to collect each TestCase's decorated fixture methods at
    runtime. It is implemented as a metaclass so we can determine the order in which
    fixture methods are defined.
    """
    __test__ = False

    def __init__(cls, name, bases, dct):

        for member_name, member in dct.iteritems():
            if member_name.startswith('test') and isinstance(member, types.FunctionType):
                if not hasattr(member, '_suites'):
                    member._suites = set()

        super(MetaTestCase, cls).__init__(name, bases, dct)

    @classmethod
    def _cmp_str(cls, instance):
        """Return a canonical representation of a TestCase for sorting and hashing."""
        return "%s.%s" % (instance.__module__, instance.__name__)

    def __cmp__(self, other):
        """Sort TestCases by a particular string representation."""
        return cmp(MetaTestCase._cmp_str(self), MetaTestCase._cmp_str(other))

    def bucket(self, bucket_count, bucket_salt=None):
        """Bucket a TestCase using a relatively consistant hash - for dividing tests across runners."""
        if bucket_salt:
            return hash(MetaTestCase._cmp_str(self) + bucket_salt) % bucket_count
        else:
            return hash(MetaTestCase._cmp_str(self)) % bucket_count



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

    EVENT_ON_RUN_TEST_METHOD = 1
    EVENT_ON_COMPLETE_TEST_METHOD = 2
    EVENT_ON_RUN_CLASS_SETUP_METHOD = 3
    EVENT_ON_COMPLETE_CLASS_SETUP_METHOD = 4
    EVENT_ON_RUN_CLASS_TEARDOWN_METHOD = 5
    EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD = 6
    EVENT_ON_RUN_TEST_CASE = 7
    EVENT_ON_COMPLETE_TEST_CASE = 8

    log = class_logger.ClassLogger()

    def __init__(self, *args, **kwargs):
        super(TestCase, self).__init__()

        self._method_level = False

        # ascend the class hierarchy and discover fixture methods
        self.__init_fixture_methods()

        self.__suites_include = kwargs.get('suites_include', set())
        self.__suites_exclude = kwargs.get('suites_exclude', set())
        self.__suites_require = kwargs.get('suites_require', set())
        self.__name_overrides = kwargs.get('name_overrides', None)

        self.__debugger = kwargs.get('debugger')

        # callbacks for various stages of execution, used for stuff like logging
        self.__callbacks = defaultdict(list)

        # one of these will later be populated with exception info if there's an
        # exception in the class_setup/class_teardown stage
        self.__class_level_failure = None
        self.__class_level_error = None

        # for now, we still support the use of unittest-style assertions defined on the TestCase instance
        for name in dir(deprecated_assertions):
            if name.startswith(('assert', 'fail')):
                setattr(self, name, instancemethod(getattr(deprecated_assertions, name), self, self.__class__))

        self.failure_limit = kwargs.pop('failure_limit', None)
        self.failure_count = 0

    def __init_fixture_methods(self):
        """Initialize and populate the lists of fixture methods for this TestCase.

        Fixture methods are identified by the fixture_decorator_factory when the
        methods are created. This means in order to figure out all the fixtures
        this particular TestCase will need, we have to test all of its attributes
        for 'fixture-ness'.

        See __fixture_decorator_factory for more info.
        """
        # init our self.(class_setup|setup|teardown|class_teardown)_fixtures lists
        for fixture_type in FIXTURE_TYPES:
            setattr(self, "%s_fixtures" % fixture_type, [])

        # the list of classes in our heirarchy, starting with the highest class
        # (object), and ending with our class
        reverse_mro_list = [x for x in reversed(type(self).mro())]

        # discover which fixures are on this class, including mixed-in ones
        self._fixture_methods = defaultdict(list)

        # we want to know everything on this class (including stuff inherited
        # from bases), but we don't want to trigger any lazily loaded
        # attributes, so dir() isn't an option; this traverses __bases__/__dict__
        # correctly for us.
        for classified_attr in inspect.classify_class_attrs(type(self)):
            # have to index here for Python 2.5 compatibility
            attr_name = classified_attr[0]
            unbound_method = classified_attr[3]
            defining_class = classified_attr[2]

            # skip everything that's not a function/method
            if not inspect.isroutine(unbound_method):
                continue

            # if this is an old setUp/tearDown/etc, tag it as a fixture
            if attr_name in DEPRECATED_FIXTURE_TYPE_MAP:
                fixture_type = DEPRECATED_FIXTURE_TYPE_MAP[attr_name]
                fixture_decorator = globals()[fixture_type]
                unbound_method = fixture_decorator(unbound_method)

            # collect all of our fixtures in appropriate buckets
            if inspection.is_fixture_method(unbound_method):
                # where in our MRO this fixture was defined
                defining_class_depth = reverse_mro_list.index(defining_class)
                inspection.callable_setattr(
                        unbound_method,
                        '_defining_class_depth',
                        defining_class_depth,
                )

                # we grabbed this from the class and need to bind it to us
                instance_method = instancemethod(unbound_method, self, self.__class__)
                self._fixture_methods[instance_method._fixture_type].append(instance_method)

        # arrange our fixture buckets appropriately
        for fixture_type, fixture_methods in self._fixture_methods.iteritems():
            # sort our fixtures in order of oldest (smaller id) to newest, but
            # also grouped by class to correctly place deprecated fixtures
            fixture_methods.sort(key=lambda x: (x._defining_class_depth, x._fixture_id))

            # for setup methods, we want methods defined further back in the
            # class hierarchy to execute first.  for teardown methods though,
            # we want the opposite while still maintaining the class-level
            # definition order, so we reverse only on class depth.
            if fixture_type in REVERSED_FIXTURE_TYPES:
                fixture_methods.sort(key=lambda x: x._defining_class_depth, reverse=True)

            fixture_list_name = "%s_fixtures" % fixture_type
            setattr(self, fixture_list_name, fixture_methods)

    def _generate_test_method(self, method_name, function):
        """Allow tests to define new test methods in their __init__'s and have appropriate suites applied."""
        suite(*getattr(self, '_suites', set()))(function)
        setattr(self, method_name, instancemethod(function, self, self.__class__))

    def runnable_test_methods(self):
        """Generator method to yield runnable test methods.

        This will pick out the test methods from this TestCase, and then exclude any in
        any of our exclude_suites.  If there are any include_suites, it will then further
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
            # if there are any include suites, only run methods in them
            if self.__suites_include and not (self.__suites_include & member_suites):
                continue
            # if there are any require suites, only run methods in *all* of those suites
            if self.__suites_require and not ((self.__suites_require & member_suites) == self.__suites_require):
                continue

            # if there are any name overrides, only run the named methods
            if self.__name_overrides is None or member.__name__ in self.__name_overrides:
                yield member

    def run(self):
        """Delegator method encapsulating the flow for executing a TestCase instance.

        This method tracks its progress in a TestResult with test_method 'run'.
        This TestResult is used as a signal when running in client/server mode:
        when the client is done running a TestCase and its fixtures, it sends
        this TestResult to the server during the EVENT_ON_COMPLETE_TEST_CASE
        phase.

        This could be handled better. See
        https://github.com/Yelp/Testify/issues/121.
        """

        # The TestResult constructor wants an actual method, which it inspects
        # to determine the method name (and class name, so it must be a method
        # and not a function!). self.run is as good a method as any.
        test_case_result = TestResult(self.run)
        test_case_result.start()
        self.fire_event(self.EVENT_ON_RUN_TEST_CASE, test_case_result)

        fixtures = []
        all_class_fixtures = self.class_setup_fixtures + self.class_setup_teardown_fixtures + self.class_teardown_fixtures
        for fixture in sorted(all_class_fixtures, key=make_sortable_fixture_key):
            # We convert all class-level fixtures to
            # class_setup_teardown fixtures a) to handle all
            # class-level fixtures the same and b) to make the
            # behavior more predictable when a TestCase has different
            # fixtures interacting.
            if fixture._fixture_type == 'class_teardown':
                fixture = self.__convert_class_teardown_to_class_setup_teardown(fixture)
            elif fixture._fixture_type == 'class_setup':
                fixture = self.__convert_class_setup_to_class_setup_teardown(fixture)
            fixtures.append(fixture)

        self.__enter_class_context_managers(fixtures, self.__run_test_methods)

        test_case_result.end_in_success()
        self.fire_event(self.EVENT_ON_COMPLETE_TEST_CASE, test_case_result)

    def __convert_class_setup_to_class_setup_teardown(self, fixture):
        def wrapper(self):
            fixture()
            yield
        wrapper.__name__ = fixture.__name__
        wrapper.__doc__ = fixture.__doc__
        wrapper._fixture_type = fixture._fixture_type
        wrapper._fixture_id = fixture._fixture_id
        wrapper._defining_class_depth = fixture._defining_class_depth
        return instancemethod(wrapper, self, self.__class__)

    def __convert_class_teardown_to_class_setup_teardown(self, fixture):
        def wrapper(self):
            yield
            fixture()
        wrapper.__name__ = fixture.__name__
        wrapper.__doc__ = fixture.__doc__
        wrapper._fixture_type = fixture._fixture_type
        wrapper._fixture_id = fixture._fixture_id
        wrapper._defining_class_depth = fixture._defining_class_depth
        return instancemethod(wrapper, self, self.__class__)

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

    def method_excluded(self, method):
        """Given this TestCase's included/excluded suites, is this test method excluded?

        Returns a set of the excluded suites that the argument method is in, or an empty
        suite if none.
        """
        method_suites = set(getattr(method, '_suites', set()))
        return (self.__suites_exclude & method_suites)

    def __run_class_fixture(self, fixture_method, function_to_call, stage, callback_on_run_event, callback_on_complete_event, fire_events=True):
        self._stage = stage

        result = TestResult(fixture_method)
        try:
            result.start()
            if fire_events:
                self.fire_event(callback_on_run_event, result)
            if self.__execute_block_recording_exceptions(function_to_call, result, is_class_level=True):
                result.end_in_success()
            else:
                self.failure_count += 1
        except (KeyboardInterrupt, SystemExit):
            result.end_in_interruption(sys.exc_info())
            raise
        finally:
            if fire_events:
                self.fire_event(callback_on_complete_event, result)

    def __enter_class_context_managers(self, fixture_methods, callback):
        """Transform each fixture_method into a context manager with
        contextlib.contextmanager, enter them recursively, and call
        callback.
        """
        if fixture_methods:
            fixture_method = fixture_methods[0]
            ctm = contextmanager(fixture_method)()

            if fixture_method._fixture_type == 'class_teardown':
                # class_teardown fixture is wrapped as
                # class_setup_teardown. We should not fire events for the
                # setup phase of this fake context manager.
                fire_events = False
            else:
                fire_events = True

            self.__run_class_fixture(
                fixture_method,
                ctm.__enter__,
                self.STAGE_CLASS_SETUP,
                self.EVENT_ON_RUN_CLASS_SETUP_METHOD,
                self.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD,
                fire_events
            )

            self.__enter_class_context_managers(fixture_methods[1:], callback)

            if fixture_method._fixture_type == 'class_setup':
                # class_setup fixture is wrapped as
                # class_setup_teardown. We should not fire events for the
                # teardown phase of this fake context manager.
                fire_events = False
            else:
                fire_events = True

            self.__run_class_fixture(
                fixture_method,
                lambda: ctm.__exit__(None, None, None),
                self.STAGE_CLASS_TEARDOWN,
                self.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD,
                self.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD,
                fire_events
            )
        else:
            callback()

    def __enter_context_managers(self, fixture_methods, callback):
        """Transform each fixture_method into a context manager with
        contextlib.contextmanager, enter them recursively, and call
        callback.
        """
        if fixture_methods:
            with contextmanager(fixture_methods[0])():
                self.__enter_context_managers(fixture_methods[1:], callback)
        else:
            callback()

    def __run_test_methods(self):
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
            # fails. (Yelp's Selenium test cases do this.)
            test_method.im_self.test_result = result

            try:
                self._method_level = True # Flag that we're currently running method-level stuff (rather than class-level)

                # run "on-run" callbacks. e.g. print out the test method name
                self.fire_event(self.EVENT_ON_RUN_TEST_METHOD, result)

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
                    self.__execute_block_recording_exceptions(_setup_block, result)

                    def _run_test_block():
                        # then run the test method itself, assuming setup was successful
                        self._stage = self.STAGE_TEST_METHOD
                        if not result.complete:
                            self.__execute_block_recording_exceptions(test_method, result)

                    def _setup_teardown_block():
                        self.__enter_context_managers(self.setup_teardown_fixtures, _run_test_block)

                    # then run any setup_teardown fixtures, assuming setup was successful.
                    if not result.complete:
                        self.__execute_block_recording_exceptions(_setup_teardown_block, result)

                    # finally, run the teardown phase
                    self._stage = self.STAGE_TEARDOWN
                    for fixture_method in self.teardown_fixtures:
                        self.__execute_block_recording_exceptions(fixture_method, result)

                # if nothing's gone wrong, it's not about to start
                if not result.complete:
                    result.end_in_success()
            except (KeyboardInterrupt, SystemExit):
                result.end_in_interruption(sys.exc_info())
                raise
            finally:
                self.fire_event(self.EVENT_ON_COMPLETE_TEST_METHOD, result)
                self._method_level = False

                if not result.success:
                    self.failure_count += 1
                    if self.failure_limit and self.failure_count >= self.failure_limit:
                        return

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

    def __execute_block_recording_exceptions(self, block_fxn, result, is_class_level=False):
        """Excerpted code for executing a block of code that might raise an
        exception, requiring us to update a result object.

        Return value is a boolean describing whether the block was successfully
        executed without exceptions.
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
            # some code may want to use an alternative exc_info for an exception
            # (for instance, in an event loop). You can signal an alternative
            # stack to use by adding a _testify_exc_tb attribute to the
            # exception object
            if hasattr(exception, '_testify_exc_tb'):
                exc_info = (type(exception), exception, exception._testify_exc_tb)
            else:
                exc_info = sys.exc_info()
            if isinstance(exception, AssertionError):
                result.end_in_failure(exc_info)
                if is_class_level:
                    self.__class_level_failure = exc_info
            else:
                result.end_in_error(exc_info)
                if is_class_level:
                    self.__class_level_error = exc_info
            if self.__debugger:
                exc, val, tb = exc_info
                print "\nDEBUGGER"
                print "\n".join(result.format_exception_info())
                import ipdb
                ipdb.post_mortem(tb)
            return False
        else:
            return True

    def classSetUp(self): pass
    def setUp(self): pass
    def tearDown(self): pass
    def classTearDown(self): pass
    def runTest(self): pass


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
        for member_name, member in default_test_case_dict.iteritems():
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
            function._suites = set(function._suites) | set(args)
            if reason:
                if not hasattr(function, '_suite_reasons'):
                    function._suite_reasons = []
                function._suite_reasons.append(reason)
        return function

    return mark_test_with_suites


# unique id for fixtures
_fixture_id = [0]

def __fixture_decorator_factory(fixture_type):
    """Decorator generator for the fixture decorators.

    Tagging a class/instancemethod as 'setup', etc, will mark the method with a
    _fixture_id. Smaller fixture ids correspond to functions higher on the
    class hierarchy, since base classes (and their methods!) are created before
    their children.

    When our test cases are instantiated, they use this _fixture_id to sort
    methods into the appropriate _fixture_methods bucket. Note that this
    sorting cannot be done here, because this decorator does not recieve
    instancemethods -- which would be aware of their class -- because the class
    they belong to has not yet been created.

    **NOTE**: This means fixtures of the same type on a class will be executed
    in the order that they are defined, before/after fixtures execute on the
    parent class execute setups/teardowns, respectively.
    """

    def fixture_decorator(callable_):
        # Decorators act on *functions*, so we need to take care when dynamically
        # decorating class attributes (which are (un)bound methods).
        function = inspection.get_function(callable_)

        # record the fixture type and id for this function
        function._fixture_type = fixture_type

        if function.__name__ in DEPRECATED_FIXTURE_TYPE_MAP:
            # we push deprecated setUps/tearDowns to the beginning or end of
            # our fixture lists, respectively. this is the best we can do,
            # because these methods are generated in the order their classes
            # are created, so we can't assign a fair fixture_id to them.
            function._fixture_id = 0 if fixture_type.endswith('setup') else float('inf')
        else:
            # however, if we've tagged a fixture with our decorators then we
            # effectively register their place on the class hierarchy by this
            # fixture_id.
            function._fixture_id = _fixture_id[0]

        _fixture_id[0] += 1

        return function

    fixture_decorator.__name__ = fixture_type

    return fixture_decorator

class_setup = __fixture_decorator_factory('class_setup')
setup = __fixture_decorator_factory('setup')
teardown = __fixture_decorator_factory('teardown')
class_teardown = __fixture_decorator_factory('class_teardown')
setup_teardown = __fixture_decorator_factory('setup_teardown')
class_setup_teardown = __fixture_decorator_factory('class_setup_teardown')


class let(object):
    """Decorator that creates a lazy-evaluated helper property. The value is
    cached across multiple calls in the same test, but not across multiple
    tests.
    """

    _unsaved = []

    def __init__(self, func):
        self._func = func
        self._result = self._unsaved

    def __get__(self, test_case, cls):
        if test_case is None:
            return self
        if self._result is self._unsaved:
            self.__set__(test_case, self._func(test_case))
        return self._result

    def __set__(self, test_case, value):
        self._save_result(value)
        self._register_reset_after_test_completion(test_case)

    def _save_result(self, result):
        self._result = result

    def _register_reset_after_test_completion(self, test_case):
        test_case.register_callback(
                TestCase.EVENT_ON_COMPLETE_TEST_METHOD,
                lambda _: self._reset_value(),
        )

    def _reset_value(self):
        self._result = self._unsaved

# vim: set ts=4 sts=4 sw=4 et:
