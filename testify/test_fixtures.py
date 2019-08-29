import contextlib
import inspect
import itertools

import six

from testify.utils import inspection
from testify.test_result import TestResult

__testify = 1


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

TEARDOWN_FIXTURES = ['teardown', 'class_teardown']

SETUP_FIXTURES = ['setup', 'class_setup']

HYBRID_FIXTURES = ['setup_teardown', 'class_setup_teardown']


class TestFixtures(object):
    """
    Handles all the juggling of actual fixture methods and the context they are
    supposed to provide our tests.
    """

    def __init__(self, class_fixtures, instance_fixtures):
        # We convert all class-level fixtures to
        # class_setup_teardown fixtures a) to handle all
        # class-level fixtures the same and b) to make the
        # behavior more predictable when a TestCase has different
        # fixtures interacting.
        self.class_fixtures = self.sort(
            self.ensure_generator(f) for f in class_fixtures
        )
        self.instance_fixtures = self.sort(
            self.ensure_generator(f) for f in instance_fixtures
        )

    def ensure_generator(self, fixture):
        if fixture._fixture_type in HYBRID_FIXTURES:
            # already a context manager, nothing to do
            return fixture

        if fixture._fixture_type in SETUP_FIXTURES:
            def wrapper(self):
                fixture()
                yield
        elif fixture._fixture_type in TEARDOWN_FIXTURES:
            def wrapper(self):
                yield
                fixture()

        wrapper.__name__ = fixture.__name__
        wrapper.__doc__ = fixture.__doc__
        wrapper._fixture_type = fixture._fixture_type
        wrapper._fixture_id = fixture._fixture_id
        wrapper._defining_class_depth = fixture._defining_class_depth

        # http://stackoverflow.com/q/4364565
        func_self = six.get_method_self(fixture)
        assert func_self is not None
        return wrapper.__get__(func_self, type(func_self))

    @contextlib.contextmanager
    def class_context(self, setup_callbacks=None, teardown_callbacks=None):
        with self.enter(self.class_fixtures, setup_callbacks, teardown_callbacks) as fixture_failures:
            yield fixture_failures

    @contextlib.contextmanager
    def instance_context(self):
        with self.enter(self.instance_fixtures) as fixture_failures:
            yield fixture_failures

    @contextlib.contextmanager
    def enter(self, fixtures, setup_callbacks=None, teardown_callbacks=None, stop_setups=False):
        """Transform each fixture_method into a context manager, enter them
        recursively, and yield any failures.

        `stop_setups` is set after a setup fixture fails. This flag prevents
        more setup fixtures from being added to the onion after a failure as we
        recurse through the list of fixtures.
        """

        # base case
        if not fixtures:
            yield []
            return

        setup_callbacks = setup_callbacks or [None, None]
        teardown_callbacks = teardown_callbacks or [None, None]

        fixture = fixtures[0]

        ctm = contextlib.contextmanager(fixture)()

        # class_teardown fixture is wrapped as
        # class_setup_teardown. We should not fire events for the
        # setup phase of this fake context manager.
        suppress_callbacks = bool(fixture._fixture_type in TEARDOWN_FIXTURES)

        # if a previous setup fixture failed, stop running new setup
        # fixtures.  this doesn't apply to teardown fixtures, however,
        # because behind the scenes they're setup_teardowns, and we need
        # to run the (empty) setup portion in order to get the teardown
        # portion later.
        if not stop_setups or fixture._fixture_type in TEARDOWN_FIXTURES:
            enter_failures = self.run_fixture(
                fixture,
                ctm.__enter__,
                enter_callback=None if suppress_callbacks else setup_callbacks[0],
                exit_callback=None if suppress_callbacks else setup_callbacks[1],
            )
            # keep skipping setups once we've had a failure
            stop_setups = stop_setups or bool(enter_failures)
        else:
            # we skipped the setup, pretend like nothing happened.
            enter_failures = []

        with self.enter(fixtures[1:], setup_callbacks, teardown_callbacks, stop_setups) as all_failures:
            all_failures += enter_failures or []
            # need to only yield one failure
            yield all_failures

        # this setup fixture got skipped due to an earlier setup fixture
        # failure, or failed itself. all of these fixtures are basically
        # represented by setup_teardowns, but because we never ran this setup,
        # we have nothing to do for teardown (if we did visit it here, that
        # would have the effect of running the setup we just skipped), so
        # instead bail out and move on to the next fixture on the stack.
        if stop_setups and fixture._fixture_type in SETUP_FIXTURES:
            return

        # class_setup fixture is wrapped as
        # class_setup_teardown. We should not fire events for the
        # teardown phase of this fake context manager.
        suppress_callbacks = bool(fixture._fixture_type in SETUP_FIXTURES)

        # this is hack to finish the remainder of the context manager without
        # calling contextlib's __exit__; doing that messes up the stack trace
        # we end up with.
        def exit():
            try:
                next(ctm.gen)
            except StopIteration:
                pass

        exit_failures = self.run_fixture(
            fixture,
            exit,
            enter_callback=None if suppress_callbacks else teardown_callbacks[0],
            exit_callback=None if suppress_callbacks else teardown_callbacks[1],
        )

        all_failures += exit_failures or []

    def run_fixture(self, fixture, function_to_call, enter_callback=None, exit_callback=None):
        result = TestResult(fixture)
        try:
            result.start()
            if enter_callback:
                enter_callback(result)
            if result.record(function_to_call):
                result.end_in_success()
            else:
                return result.exception_infos
        finally:
            if exit_callback:
                exit_callback(result)

    def sort(self, fixtures):

        def key(fixture):
            """Use class depth, fixture type and fixture id to define
            a sortable key for fixtures.

            Class depth is the most significant value and defines the
            MRO (reverse mro for teardown methods) order. Fixture type
            and fixture id help us to define the expected order.

            See
            test.test_case_test.FixtureMethodRegistrationOrderWithBaseClassTest
            for the expected order.
            """
            fixture_order = {
                'class_setup': 0,
                'class_teardown': 1,
                'class_setup_teardown': 2,

                'setup': 3,
                'teardown': 4,
                'setup_teardown': 5,
            }

            if fixture._fixture_type in REVERSED_FIXTURE_TYPES:
                # class_teardown fixtures should be run in reverse
                # definition order (last definition runs
                # first). Converting fixture_id to its negative
                # value will sort class_teardown fixtures in the
                # same class in reversed order.
                return (fixture._defining_class_depth, fixture_order[fixture._fixture_type], -fixture._fixture_id)

            return (fixture._defining_class_depth, fixture_order[fixture._fixture_type], fixture._fixture_id)

        return sorted(fixtures, key=key)

    @classmethod
    def discover_from(cls, test_case):
        """Initialize and populate the lists of fixture methods for this TestCase.

        Fixture methods are identified by the fixture_decorator_factory when the
        methods are created. This means in order to figure out all the fixtures
        this particular TestCase will need, we have to test all of its attributes
        for 'fixture-ness'.

        See __fixture_decorator_factory for more info.
        """

        all_fixtures = {}
        for fixture_type in FIXTURE_TYPES:
            all_fixtures[fixture_type] = []

        # the list of classes in our heirarchy, starting with the highest class
        # (object), and ending with our class
        test_class = type(test_case)
        mro = inspect.getmro(test_class)
        reverse_mro_index = {
            cls: i for (i, cls) in enumerate(reversed(mro))}

        # discover which fixures are on this class, including mixed-in ones

        # We want to know everything on this class (including stuff inherited
        # from bases), AND where it came from.  This code is based on
        # classify_class_attrs from the inspect module, which does just that.
        # (classify_class_attrs isn't used here because it does a bunch of
        # relatively slow checks for the type of the attribute, which we then
        # completely ignore.)
        for name in dir(test_class):
            # Try __dict__ first, to subvert descriptor magic when possible
            # (important for e.g. methods)
            if name in test_class.__dict__:
                obj = test_class.__dict__[name]
            else:
                obj = getattr(test_class, name)

            # Figure out where it came from
            defining_class = getattr(obj, '__objclass__', None)
            if defining_class is None:
                for base in mro:
                    if name in base.__dict__:
                        defining_class = base
                        break

            # Re-fetch the object, to get it from its owning __dict__ instead
            # of a getattr, if possible.  Don't know why, but inspect does it!
            if defining_class is not None and name in defining_class.__dict__:
                obj = defining_class.__dict__[name]

            # End inspection; now this is testify logic.

            if inspection.is_fixture_method(obj):
                fixture_method = obj
            elif (name in DEPRECATED_FIXTURE_TYPE_MAP and
                    inspect.isroutine(obj)):
                # if this is an old setUp/tearDown/etc, tag it as a fixture
                fixture_type = DEPRECATED_FIXTURE_TYPE_MAP[name]
                fixture_decorator = globals()[fixture_type]
                fixture_method = fixture_decorator(obj)
            else:
                continue

            depth = reverse_mro_index[defining_class]
            fixture_method._defining_class_depth = depth

            # We grabbed this from the class and need to bind it to the test
            # case
            # http://stackoverflow.com/q/4364565
            instance_method = fixture_method.__get__(test_case, test_class)
            all_fixtures[instance_method._fixture_type].append(instance_method)

        class_level = ['class_setup', 'class_teardown', 'class_setup_teardown']
        inst_level = ['setup', 'teardown', 'setup_teardown']

        return cls(
            class_fixtures=list(itertools.chain(*[all_fixtures[typ] for typ in class_level])),
            instance_fixtures=list(itertools.chain(*[all_fixtures[typ] for typ in inst_level])),
        )


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
            test_case.EVENT_ON_COMPLETE_TEST_METHOD,
            lambda _: self._reset_value(),
        )

    def _reset_value(self):
        self._result = self._unsaved

# vim: set ts=4 sts=4 sw=4 et:
