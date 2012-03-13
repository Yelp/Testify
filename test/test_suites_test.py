from testify import TestCase, run, assert_equal, MetaTestCase, suite

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