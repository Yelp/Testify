from testify import TestCase, assert_equal, suite
from testify.test_runner import TestRunner

_suites = ['module-level']


class TestSuitesTest(TestCase):

    def test_subclass_suites_doesnt_affect_superclass_suites(self):
        """Check that setting _suites in a subclass only affects that subclass, not the superclass.
        Checking https://github.com/Yelp/Testify/issues/53"""
        class SuperTestCase(TestCase):
            _suites = ['super']
            def test_thing(self):
                pass

        class SubTestCase(SuperTestCase):
            _suites = ['sub']

        # If we set suites_require=['super'], then only the superclass should have a method to run.
        super_instance = SuperTestCase(suites_require=set(['super']))
        sub_instance = SubTestCase(suites_require=set(['super']))

        assert_equal(list(super_instance.runnable_test_methods()), [super_instance.test_thing])
        assert_equal(list(sub_instance.runnable_test_methods()), [])

        # Conversely, if we set suites_require=['sub'], then only the subclass should have a method to run.
        super_instance = SuperTestCase(suites_require=set(['sub']))
        sub_instance = SubTestCase(suites_require=set(['sub']))

        assert_equal(list(super_instance.runnable_test_methods()), [])
        assert_equal(list(sub_instance.runnable_test_methods()), [sub_instance.test_thing])

    def test_suite_decorator_overrides_parent(self):
        """Check that the @suite decorator overrides any @suite on the overridden (parent class) method."""
        class SuperTestCase(TestCase):
            @suite('super')
            def test_thing(self):
                pass

        class SubTestCase(SuperTestCase):
            __test__ = False

            @suite('sub')
            def test_thing(self):
                pass

        super_instance = SuperTestCase()
        sub_instance = SubTestCase()

        assert_equal(super_instance.test_thing._suites, set(['super']))
        assert_equal(sub_instance.test_thing._suites, set(['sub']))


class ListSuitesTestCase(TestCase):
    _suites = ['external-api']

    def __init__(self, **kwargs):
        super(ListSuitesTestCase, self).__init__(**kwargs)

        # add a dynamic test to guard against
        # https://github.com/Yelp/Testify/issues/85
        from types import MethodType
        test = MethodType(lambda self: True, self, type(self))
        setattr(self, 'test_foo', test)

    @suite('disabled', 'crazy', conditions=True)
    def test_disabled(self): True

    @suite('disabled', reason='blah')
    def test_also_disabled(self): True

    @suite('not-applied', conditions=False)
    def test_not_disabled(self): True

    def test_list_suites(self):
        test_runner = TestRunner(type(self))
        assert_equal(test_runner.list_suites(), {
            'disabled': '2 tests',
            'module-level': '5 tests',
            'external-api': '5 tests',
            'crazy': '1 tests',
        })

