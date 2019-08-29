import itertools

from testify import assert_equal
from testify import assert_not_equal
from testify import class_setup
from testify import class_setup_teardown
from testify import class_teardown
from testify import let
from testify import setup
from testify import setup_teardown
from testify import suite
from testify import teardown
from testify import TestCase


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
    def just_class_teardown(self):
        assert_equal(self.counter, 18)
        self.counter += 1

    @class_teardown
    def __class_teardown_postrun_1(self):
        assert_equal(self.counter, 19)
        self.counter += 1

    @class_teardown
    def __class_teardown_postrun_2(self):
        assert_equal(self.counter, 20)


class FixtureMethodRegistrationOrderWithBaseClassTest(TestCase):
    """Test that registered fixtures execute in the expected order, which is:
     - class_setup & enter class_setup_teardown of the Base class
     - class_setup & enter class_setup_teardown of the Derived class
     - exit class_setup_teardown & class_teardown of the Derived class
     - exit class_setup_teardown & class_teardown of the Base class
    """

    class FakeBaseClass(TestCase):

        def __init__(self, *args, **kwargs):
            super(FixtureMethodRegistrationOrderWithBaseClassTest.FakeBaseClass, self).__init__(*args, **kwargs)
            self.method_order = []

        def classSetUp(self):
            self.method_order.append("base_classSetUp")

        def classTearDown(self):
            self.method_order.append("base_classTearDown")

        @class_setup
        def base_class_setup(self):
            self.method_order.append("base_class_setup")

        @class_setup_teardown
        def base_class_setup_teardown(self):
            self.method_order.append("base_class_setup_teardown_setup_phase")
            yield
            self.method_order.append("base_class_setup_teardown_teardown_phase")

        @class_teardown
        def base_class_teardown(self):
            self.method_order.append("base_class_teardown")

        @setup_teardown
        def base_instance_setup_teardown(self):
            self.method_order.append("base_instance_setup_teardown_setup_phase")
            yield
            self.method_order.append("base_instance_setup_teardown_teardown_phase")

        @setup
        def base_instance_setup(self):
            self.method_order.append("base_instance_setup")

        @teardown
        def base_instance_teardown(self):
            self.method_order.append("base_instance_teardown")

        def test_something(self):
            """Need a test method to get instance-level fixtures to run."""
            return True

    class FakeDerivedClass(FakeBaseClass):
        @class_setup
        def derived_class_setup(self):
            self.method_order.append("derived_class_setup")

        @class_setup_teardown
        def derived_class_setup_teardown(self):
            self.method_order.append("derived_class_setup_teardown_setup_phase")
            yield
            self.method_order.append("derived_class_setup_teardown_teardown_phase")

        @class_teardown
        def derived_class_teardown(self):
            self.method_order.append("derived_class_teardown")

        @setup_teardown
        def base_derived_setup_teardown(self):
            self.method_order.append("derived_instance_setup_teardown_setup_phase")
            yield
            self.method_order.append("derived_instance_setup_teardown_teardown_phase")

        @setup
        def derived_instance_setup(self):
            self.method_order.append("derived_instance_setup")

        @teardown
        def derived_instance_teardown(self):
            self.method_order.append("derived_instance_teardown")

    class FakeDerivedClassWithDeprecatedClassLevelFixtures(FakeBaseClass):
        def classSetUp(self):
            self.method_order.append("derived_classSetUp")

        def classTearDown(self):
            self.method_order.append("derived_classTearDown")

        @class_setup
        def derived_class_setup(self):
            self.method_order.append("derived_class_setup")

        @class_setup_teardown
        def derived_class_setup_teardown(self):
            self.method_order.append("derived_class_setup_teardown_setup_phase")
            yield
            self.method_order.append("derived_class_setup_teardown_teardown_phase")

        @class_teardown
        def derived_class_teardown(self):
            self.method_order.append("derived_class_teardown")

    def test_order(self):
        fake_test_case = self.FakeDerivedClass()
        fake_test_case.run()
        expected_order = [
            "base_classSetUp",
            "base_class_setup",
            "base_class_setup_teardown_setup_phase",

            "derived_class_setup",
            "derived_class_setup_teardown_setup_phase",

            "base_instance_setup",
            "base_instance_setup_teardown_setup_phase",

            "derived_instance_setup",
            "derived_instance_setup_teardown_setup_phase",

            "derived_instance_setup_teardown_teardown_phase",
            "derived_instance_teardown",

            "base_instance_setup_teardown_teardown_phase",
            "base_instance_teardown",

            "derived_class_setup_teardown_teardown_phase",
            "derived_class_teardown",

            "base_class_setup_teardown_teardown_phase",
            "base_class_teardown",
            "base_classTearDown",
        ]

        assert_equal(fake_test_case.method_order, expected_order)

    def test_order_with_deprecated_class_level_fixtures_in_derived_class(self):
        fake_test_case = self.FakeDerivedClassWithDeprecatedClassLevelFixtures()
        fake_test_case.run()
        expected_order = [
            "base_class_setup",
            "base_class_setup_teardown_setup_phase",

            "derived_classSetUp",
            "derived_class_setup",
            "derived_class_setup_teardown_setup_phase",

            "base_instance_setup",
            "base_instance_setup_teardown_setup_phase",

            "base_instance_setup_teardown_teardown_phase",
            "base_instance_teardown",

            "derived_class_setup_teardown_teardown_phase",
            "derived_class_teardown",
            "derived_classTearDown",

            "base_class_setup_teardown_teardown_phase",
            "base_class_teardown",
        ]

        assert_equal(fake_test_case.method_order, expected_order)


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


@class_setup
def test_incorrectly_defined_fixture():
    """Not a true test, but declarations like this shouldn't crash."""
    pass


class FixtureMixin(object):
    @class_setup
    def set_attr(cls):
        cls.foo = True

    @property
    def get_foo(self):
        # properties dependent on setup shouldn't crash our dir() loop when
        # determining fixures on a class
        return self.foo

    def test_foo(self):
        self.foo_ran = self.get_foo


class TestFixtureMixinsGetRun(TestCase, FixtureMixin):
    # define the teardown here in case the mixin doesn't properly apply it
    @class_teardown
    def make_sure_i_ran(self):
        assert self.foo_ran


class RedefinedFixtureWithNoDecoratorTest(TestCase, FixtureMixin):
    def set_attr(self):
        pass

    def test_foo(self):
        # set_attr shouldn't have run because it's no longer decorated
        assert not hasattr(self, 'foo')


class TestSubclassedCasesWithFeatureMixinsGetRun(TestFixtureMixinsGetRun):
    pass


class TestOtherCasesWithSameFixtureMixinsGetRun(TestCase, FixtureMixin):
    @teardown
    def make_sure_i_ran(self):
        assert self.foo_ran


class NewerFixtureMixin(object):
    @class_setup
    def set_another_attr(cls):
        assert cls.foo  # this setup should run after FixtureMixin's
        cls.bar = True

    def test_bar(self):
        self.bar_ran = self.bar


class TestFixtureMixinOrder(TestCase, NewerFixtureMixin, FixtureMixin):
    @class_teardown
    def make_sure_i_ran(self):
        assert self.foo_ran
        assert self.bar_ran


class DeprecatedFixtureOrderTestBase(TestCase):
    @class_setup
    def set_something(self):
        assert not hasattr(self, 'something')
        self.something = True

    @class_teardown
    def clear_something(self):
        assert self.something is None


class DeprecatedFixtureOrderTestChild(DeprecatedFixtureOrderTestBase):
    """Tests that deprecated fixtures on children are called in the correct order."""

    def classSetUp(self):
        """Should be called after do_something."""
        assert self.something is True
        self.something = False

    def test_something(self):
        assert self.something is False

    def classTearDown(self):
        """Should be called before clear_something"""
        assert self.something is False
        self.something = None


class FixtureOverloadTestBase(TestCase):
    foo = True

    @setup
    def unset_foo(self):
        self.foo = False


class FixtureOverloadTestChild(FixtureOverloadTestBase):
    """Tests that overloading a fixture works as expected."""
    @setup
    def unset_foo(self):
        pass

    def test_overloaded_setup(self):
        # we shouldn't have unset this
        assert self.foo


class LetTest(TestCase):

    @let
    def counter(self):
        return itertools.count(0)

    def test_first_call_is_not_cached(self):
        assert_equal(next(self.counter), 0)

    def test_subsequent_calls_are_cached(self):
        assert_equal(next(self.counter), 0)
        assert_equal(next(self.counter), 1)


class LetWithLambdaTest(TestCase):

    counter = let(lambda self: itertools.count(0))

    def test_first_call_is_not_cached(self):
        assert_equal(next(self.counter), 0)

    def test_subsequent_calls_are_cached(self):
        assert_equal(next(self.counter), 0)
        assert_equal(next(self.counter), 1)


class LetWithSubclassTest(LetWithLambdaTest):
    """Test that @let is inherited correctly."""
    pass


class SuiteDecoratorTest(TestCase):

    def test_suite_pollution_with_suites_attribute(self):
        """Test if suite decorator modifies the object's attribute
        objects instead of assigning a new object. Modifying _suite
        attribute objects causes suite pollution in TestCases.

        Here we test if the _suites attribute's id() remains the same
        to verify suite decorator does not modify the object's
        attribute object.
        """

        def function_to_decorate():
            pass

        function_to_decorate._suites = {'fake_suite_1'}

        suites_before_decoration = function_to_decorate._suites

        function_to_decorate = suite('fake_suite_2')(function_to_decorate)

        suites_after_decoration = function_to_decorate._suites

        assert_not_equal(
            id(suites_before_decoration),
            id(suites_after_decoration),
            "suites decorator modifies the object's _suite attribute"
        )

# vim: set ts=4 sts=4 sw=4 et:
