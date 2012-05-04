import itertools

from testify import TestCase
from testify import assert_equal
from testify import class_setup
from testify import class_setup_teardown
from testify import class_teardown
from testify import let
from testify import run
from testify import setup
from testify import setup_teardown
from testify import teardown


class TestMethodsGetRun(TestCase):
    def test_method_1(self):
        self.test_1_run = True

    def test_method_2(self):
        self.test_2_run = True

    @class_teardown
    def assert_test_methods_were_run(self):
        assert self.test_1_run
        assert self.test_2_run

class DeprecatedClassSetupFixturesGetRun(TestCase):
    def classSetUp(self):
        self.test_var = True

    def test_test_var(self):
        assert self.test_var

class DeprecatedSetupFixturesGetRun(TestCase):
    def setUp(self):
        self.test_var = True

    def test_test_var(self):
        assert self.test_var

class DeprecatedTeardownFixturesGetRun(TestCase):
    COUNTER = 0

    def tearDown(self):
        self.test_var = True

    def test_test_var_pass_1(self):
        self.COUNTER += 1
        if self.COUNTER > 1:
            assert self.test_var

    def test_test_var_pass_2(self):
        self.COUNTER += 1
        if self.COUNTER > 1:
            assert self.test_var

class DeprecatedClassTeardownFixturesGetRun(TestCase):
    def test_placeholder(self):
        pass

    def class_teardown(self):
        self.test_var = True

    @class_teardown
    def test_test_var(self):
        assert self.test_var

class ClassSetupFixturesGetRun(TestCase):
    @class_setup
    def set_test_var(self):
        self.test_var = True

    def test_test_var(self):
        assert self.test_var

class SetupFixturesGetRun(TestCase):
    @setup
    def set_test_var(self):
        self.test_var = True

    def test_test_var(self):
        assert self.test_var

class TeardownFixturesGetRun(TestCase):
    COUNTER = 0

    @teardown
    def set_test_var(self):
        self.test_var = True

    def test_test_var_first_pass(self):
        self.COUNTER += 1
        if self.COUNTER > 1:
            assert self.test_var

    def test_test_var_second_pass(self):
        self.COUNTER += 1
        if self.COUNTER > 1:
            assert self.test_var

class TestRegisterFixtureMethodsParentClass(TestCase):
    """A parent class to test the ability to register fixture methods"""

    @setup
    def parent_setup_1(self):
        """Set an instance variable to test that this method gets called"""
        self.parent_setup_exists = 1

    @setup
    def __parent_setup_2(self):
        """Set an instance variable to test that this method gets called"""
        self.parent_setup_exists += 1

class TestRegisterFixtureMethodsChildClass(TestRegisterFixtureMethodsParentClass):
    """A child class to test the ability to register fixture methods"""

    @setup
    def __zchild_setup_1(self):
        self.child_setup_exists = self.parent_setup_exists + 1

    @setup
    def __child_setup_2(self):
        self.child_setup_2_exists = self.child_setup_exists + 1

    def test_things_exist(self):
        """Check for instance variable set by fixture method from parent class"""
        self.failUnless(self.parent_setup_exists == 2)
        assert self.child_setup_exists == 3
        assert self.child_setup_2_exists == 4

class FixtureMethodRegistrationOrderTest(TestCase):
    """Test that registered fixtures execute in the expected order, which is:
     - class_setup
     - enter class_setup_teardown
     - setup
     - enter setup_teardown

     - test

     - exit setup_teardown, in Reverse of definition
     - teardown
     - exit class_setup_teardown in Reverse order of definition
     - class_teardown
    """
    def __init__(self, *args, **kwargs):
        super(FixtureMethodRegistrationOrderTest, self).__init__(*args, **kwargs)
        self.counter = 0

    @class_setup
    def __class_setup_prerun_1(self):
        assert_equal(self.counter, 0)
        self.counter += 1

    @class_setup
    def __class_setup_prerun_2(self):
        assert_equal(self.counter, 1)
        self.counter += 1

    @class_setup
    def third_setup(self):
        assert_equal(self.counter, 2)
        self.counter += 1

    @class_setup_teardown
    def __class_context_manager_1(self):
        assert_equal(self.counter, 3)
        self.counter += 1
        yield
        assert_equal(self.counter, 17)
        self.counter += 1

    @class_setup_teardown
    def __class_context_manager_2(self):
        assert_equal(self.counter, 4)
        self.counter += 1
        yield
        assert_equal(self.counter, 16)
        self.counter += 1

    @setup
    def __setup_prerun_1(self):
        assert_equal(self.counter, 5)
        self.counter += 1

    @setup
    def __setup_prerun_2(self):
        assert_equal(self.counter, 6)
        self.counter += 1

    @setup
    def real_setup(self):
        assert_equal(self.counter, 7)
        self.counter += 1

    @setup_teardown
    def __context_manager_1(self):
        assert_equal(self.counter, 8)
        self.counter += 1
        yield
        assert_equal(self.counter, 12)
        self.counter += 1

    @setup_teardown
    def __context_manager_2(self):
        assert_equal(self.counter, 9)
        self.counter += 1
        yield
        assert_equal(self.counter, 11)
        self.counter += 1

    def test_fixture_registration_order(self):
        assert_equal(self.counter, 10)
        self.counter += 1

    @teardown
    def do_some_teardown(self):
        assert_equal(self.counter, 13)
        self.counter += 1

    @teardown
    def __zteardown_postrun_1(self):
        assert_equal(self.counter, 14)
        self.counter += 1

    @teardown
    def __teardown_postrun_2(self):
        assert_equal(self.counter, 15)
        self.counter += 1

    @class_teardown
    def jsut_class_teardown(self):
        assert_equal(self.counter, 18)
        self.counter += 1

    @class_teardown
    def __class_teardown_postrun_1(self):
        assert_equal(self.counter, 19)
        self.counter += 1

    @class_teardown
    def __class_teardown_postrun_2(self):
        assert_equal(self.counter, 20)

class OverrideTest(TestCase):
    def test_method_1(self):
        pass

    def test_method_2(self):
        pass

class LetTest(TestCase):

    @let
    def counter(self):
        return itertools.count(0)

    def test_first_call_is_not_cached(self):
        assert_equal(self.counter.next(), 0)

    def test_subsequent_calls_are_cached(self):
        assert_equal(self.counter.next(), 0)
        assert_equal(self.counter.next(), 1)

class LetWithLambdaTest(TestCase):

    counter = let(lambda self: itertools.count(0))

    def test_first_call_is_not_cached(self):
        assert_equal(self.counter.next(), 0)

    def test_subsequent_calls_are_cached(self):
        assert_equal(self.counter.next(), 0)
        assert_equal(self.counter.next(), 1)



class CallbacksGetCalledTest(TestCase):
    def test_class_fixtures_get_reported(self):
        """Make a test case, register a bunch of callbacks for class fixtures on it, and make sure the callbacks are all run in the right order."""
        class InnerTestCase(TestCase):
            def classSetUp(self):
                pass

            def classTearDown(self):
                pass

            @class_setup_teardown
            def __class_setup_teardown_1(self):
                yield

            @class_setup_teardown
            def __class_setup_teardown_2(self):
                yield

            def test_things(self):
                pass

        inner_test_case = InnerTestCase()
        events = (
            TestCase.EVENT_ON_RUN_TEST_METHOD,
            TestCase.EVENT_ON_COMPLETE_TEST_METHOD,
            TestCase.EVENT_ON_RUN_CLASS_SETUP_METHOD,
            TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD,
            TestCase.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD,
            TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD,
        )

        calls_to_callback = []

        def make_callback(event):
            def callback(result):
                calls_to_callback.append((event, result['method']['name']))
            return callback

        for event in events:
            inner_test_case.register_callback(event, make_callback(event))

        inner_test_case.run()

        assert_equal(calls_to_callback, [
            (TestCase.EVENT_ON_RUN_CLASS_SETUP_METHOD, 'classSetUp'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, 'classSetUp'),

            (TestCase.EVENT_ON_RUN_CLASS_SETUP_METHOD, '__class_setup_teardown_1'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, '__class_setup_teardown_1'),

            (TestCase.EVENT_ON_RUN_CLASS_SETUP_METHOD, '__class_setup_teardown_2'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, '__class_setup_teardown_2'),

            (TestCase.EVENT_ON_RUN_TEST_METHOD, 'test_things'),
            (TestCase.EVENT_ON_COMPLETE_TEST_METHOD, 'test_things'),

            (TestCase.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD, '__class_setup_teardown_2'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD, '__class_setup_teardown_2'),

            (TestCase.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD, '__class_setup_teardown_1'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD, '__class_setup_teardown_1'),

            (TestCase.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD, 'classTearDown'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD, 'classTearDown'),
        ])


class MultipleDecoratorsSupportedTest(TestCase):
    def test_multiple_decorators_have_appropriate_fixture_types(self):
        """Apparently people think it's convenient to decorate their fixtures with multiple fixture types.
        Make sure that the fixture accumulators each contain functions with the appropriate _fixture_type."""

        class ThreeDecoratorsTestCase(TestCase):
            @setup
            @teardown
            @class_setup
            def blah(self):
                pass

        for fixture_type in ('setup', 'teardown', 'class_setup'):
            (func,) = ThreeDecoratorsTestCase._fixture_methods[fixture_type]
            assert_equal(func._fixture_type, fixture_type)

    def test_multiple_decorators_reported_with_correct_fixture_type_and_name(self):
        """Make sure that when a method is decorated with both @class_setup and @class_teardown,
        the appropriate fixture type is reported to the right callback, and the name and class_name are correct"""
        class TwoDecoratorsTestCase(TestCase):
            @class_setup
            @class_teardown
            def why_would_you_ever_want_to_do_this(self):
                pass

        test_instance = TwoDecoratorsTestCase()

        class_setup_results = []
        class_teardown_results = []

        test_instance.register_callback(TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, class_setup_results.append)
        test_instance.register_callback(TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD, class_teardown_results.append)

        test_instance.run()

        (class_setup_result,) = [r for r in class_setup_results if r['method']['name'] != 'classSetUp']
        assert_equal(class_setup_result['method']['fixture_type'], 'class_setup')
        assert_equal(class_setup_result['method']['name'], 'why_would_you_ever_want_to_do_this')
        assert_equal(class_setup_result['method']['class'], 'TwoDecoratorsTestCase')

        (class_teardown_result,) = [r for r in class_teardown_results if r['method']['name'] != 'classTearDown']
        assert_equal(class_teardown_result['method']['fixture_type'], 'class_teardown')
        assert_equal(class_teardown_result['method']['name'], 'why_would_you_ever_want_to_do_this')
        assert_equal(class_teardown_result['method']['class'], 'TwoDecoratorsTestCase')


if __name__ == '__main__':
    run()
