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


if __name__ == '__main__':
    run()
