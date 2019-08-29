import unittest

from testify import TestCase, assert_equal, suite
from testify.test_runner import TestRunner

_suites = ['module-level']


class TestSuitesTestCase(TestCase):

    def test_subclass_suites_doesnt_affect_superclass_suites(self):
        """Check that setting _suites in a subclass only affects that subclass, not the superclass.
        Checking https://github.com/Yelp/Testify/issues/53"""
        # If we set suites_require=['super'], then only the superclass should have a method to run.
        super_instance = SuperTestCase(suites_require={'super'})
        sub_instance = SubTestCase(suites_require={'super'})

        assert_equal(list(super_instance.runnable_test_methods()), [super_instance.test_thing])
        assert_equal(list(sub_instance.runnable_test_methods()), [sub_instance.test_thing])

        # Conversely, if we set suites_require=['sub'], then only the subclass should have a method to run.
        super_instance = SuperTestCase(suites_require={'sub'})
        sub_instance = SubTestCase(suites_require={'sub'})

        assert_equal(list(super_instance.runnable_test_methods()), [])
        assert_equal(list(sub_instance.runnable_test_methods()), [sub_instance.test_thing])

    def test_suite_decorator_overrides_parent(self):
        """Check that the @suite decorator overrides any @suite on the overridden (parent class) method."""
        super_instance = SuperDecoratedTestCase()
        sub_instance = SubDecoratedTestCase()

        assert_equal(super_instance.test_thing._suites, {'super'})
        assert_equal(sub_instance.test_thing._suites, {'sub'})


@suite('example')
class ExampleTestCase(TestCase):
    pass


class SuperTestCase(ExampleTestCase):
    _suites = ['super']

    def test_thing(self):
        pass


class SubTestCase(SuperTestCase):
    _suites = ['sub']


class SuperDecoratedTestCase(ExampleTestCase):
    @suite('super')
    def test_thing(self):
        pass


class SubDecoratedTestCase(SuperDecoratedTestCase):
    @suite('sub')
    def test_thing(self):
        pass


class ListSuitesMixin(object):
    """Test that we pick up the correct suites when using --list-suites."""

    # applied to test_foo, test_disabled, test_also.., test_not.., and test_list..
    _suites = ['example', 'class-level-suite']

    def __init__(self, **kwargs):
        super(ListSuitesMixin, self).__init__(**kwargs)

        # add a dynamic test to guard against
        # https://github.com/Yelp/Testify/issues/85
        test = (lambda self: True).__get__(self, type(self))
        setattr(self, 'test_foo', test)

    @suite('disabled', 'crazy', conditions=True)
    def test_disabled(self):
        True

    @suite('disabled', reason='blah')
    def test_also_disabled(self):
        True

    @suite('not-applied', conditions=False)
    def test_not_disabled(self):
        True

    @suite('assertion')
    def test_list_suites(self):
        # for suites affecting all of this class's tests
        num_tests = len(list(self.runnable_test_methods()))

        test_runner = TestRunner(type(self))
        assert_equal(sorted(test_runner.list_suites().items()), [
            ('assertion', '1 tests'),
            ('class-level-suite', '%d tests' % num_tests),
            ('crazy', '1 tests'),
            ('disabled', '2 tests'),
            ('example', '%d tests' % num_tests),
            ('module-level', '%d tests' % num_tests),
        ])


class ListSuitesTestCase(ExampleTestCase, ListSuitesMixin):
    """Test that suites are correctly applied to Testify TestCases."""
    pass


class ListSuitesUnittestCase(unittest.TestCase, ListSuitesMixin):
    """Test that suites are correctly applied to UnitTests."""
    pass
