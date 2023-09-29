import mock
import unittest

from testify import assert_equal
from testify import assert_in
from testify import class_setup
from testify import class_setup_teardown
from testify import class_teardown
from testify import let
from testify import run
from testify import setup
from testify import teardown
from testify import TestCase
from testify.test_case import TestifiedUnitTest


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


class OverrideTest(TestCase):
    def test_method_1(self):
        pass

    def test_method_2(self):
        pass


class UnitTest(unittest.TestCase):
    # a compact way to record each step's completion
    status = [False] * 6

    def classSetUp(self):
        self.status[0] = True

    def setUp(self):
        self.status[1] = True

    def test_i_ran(self):
        self.status[2] = True

    def tearDown(self):
        self.status[3] = True

    def classTearDown(self):
        self.status[4] = True

    @teardown
    def no_really_i_tore_down(self):
        """Fixture mixins should still work as expected."""
        self.status[5] = True


class UnitTestTestYoDawg(TestCase):
    """Make sure we actually detect and run all steps in unittest.TestCases."""

    def test_unit_test_status(self):
        TestifiedUnitTest.from_unittest_case(UnitTest)().run()
        assert_equal(UnitTest.status, [True] * 6)

# The following cases test unittest.TestCase inheritance, fixtures and mixins


class BaseUnitTest(unittest.TestCase):
    done = False

    def __init__(self):
        super(BaseUnitTest, self).__init__()
        self.init = True

    def setUp(self):
        assert self.init
        assert not self.done
        self.foo = True

    def tearDown(self):
        assert self.init
        assert not self.done
        self.done = True


class DoNothingMixin(object):
    pass


class DerivedUnitTestMixinWithFixture(BaseUnitTest):
    @setup
    def set_bar(self):
        assert self.foo  # setUp runs first
        self.bar = True

    @teardown
    def not_done(self):  # tearDown runs last
        assert not self.done

    @class_teardown
    def i_ran(cls):
        cls.i_ran = True


class DerivedUnitTestWithFixturesAndTests(DerivedUnitTestMixinWithFixture, DoNothingMixin):
    def test_foo_bar(self):
        assert self.foo
        assert self.bar
        assert not self.done


class DerivedUnitTestWithAdditionalFixturesAndTests(DerivedUnitTestMixinWithFixture):
    @setup
    def set_baz(self):
        assert self.foo
        assert self.bar
        self.baz = True

    @teardown
    def clear_foo(self):
        self.foo = False

    def test_foo_bar_baz(self):
        assert self.foo
        assert self.bar
        assert self.baz


class TestDerivedUnitTestsRan(TestCase):
    def test_unit_tests_ran(self):
        assert DerivedUnitTestMixinWithFixture.i_ran
        assert DerivedUnitTestWithFixturesAndTests.i_ran
        assert DerivedUnitTestWithAdditionalFixturesAndTests.i_ran


class ClobberLetTest(TestCase):
    """Test overwritting a let does not break subsequent tests.

    Because we are unsure which test will run first, two tests will clobber a
    let that is asserted about in the other test.
    """

    @let
    def something(self):
        return 1

    @let
    def something_else(self):
        return 2

    def test_something(self):
        self.something_else = 3
        assert_equal(self.something, 1)

    def test_something_else(self):
        self.something = 4
        assert_equal(self.something_else, 2)


class TestResultDataTest(TestCase):
    """ Tests the data returned by Testify for test-results have required
    arguments/parameters or not. """

    def test_testresult_started(self):
        class InnerTestCase(TestCase):
            pass

        class TestCaseCallback(object):
            def __init__(self):
                pass

            def __call__(self, result_dict):
                self.result_dict = result_dict

        run_test_case_callback = TestCaseCallback()
        complete_test_case_callback = TestCaseCallback()
        inner_test_case = InnerTestCase()
        inner_test_case.register_callback(TestCase.EVENT_ON_RUN_TEST_CASE, run_test_case_callback)
        inner_test_case.register_callback(TestCase.EVENT_ON_COMPLETE_TEST_CASE, complete_test_case_callback)

        inner_test_case.run()

        assert 'start_time' in run_test_case_callback.result_dict
        assert run_test_case_callback.result_dict['end_time'] is None

        assert complete_test_case_callback.result_dict['end_time'] is not None
        assert complete_test_case_callback.result_dict['run_time'] is not None
        assert complete_test_case_callback.result_dict['method']['module'] is not None
        assert complete_test_case_callback.result_dict['method']['full_name'] is not None
        assert complete_test_case_callback.result_dict['method']['class'] is not None


class CallbacksGetCalledTest(TestCase):
    def test_class_fixtures_get_reported(self):
        """Make a test case, register a bunch of callbacks for class fixtures
        on it, and make sure the callbacks are all run in the right order.
        """
        class InnerTestCase(TestCase):
            def classSetUp(self):
                pass

            def classTearDown(self):
                pass

            @class_setup_teardown
            def __class_setup_teardown(self):
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
            TestCase.EVENT_ON_RUN_TEST_CASE,
            TestCase.EVENT_ON_COMPLETE_TEST_CASE,
        )

        calls_to_callback = []

        def make_callback(event):
            def callback(result):
                calls_to_callback.append((event, result['method']['name'] if result else None))
            return callback

        for event in events:
            inner_test_case.register_callback(event, make_callback(event))

        inner_test_case.run()

        assert_equal(calls_to_callback, [
            (TestCase.EVENT_ON_RUN_TEST_CASE, 'run'),
            (TestCase.EVENT_ON_RUN_CLASS_SETUP_METHOD, '__setup_extra_class_teardowns'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, '__setup_extra_class_teardowns'),

            (TestCase.EVENT_ON_RUN_CLASS_SETUP_METHOD, 'classSetUp'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, 'classSetUp'),

            (TestCase.EVENT_ON_RUN_CLASS_SETUP_METHOD, '__class_setup_teardown'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, '__class_setup_teardown'),

            (TestCase.EVENT_ON_RUN_TEST_METHOD, 'test_things'),
            (TestCase.EVENT_ON_COMPLETE_TEST_METHOD, 'test_things'),

            (TestCase.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD, '__class_setup_teardown'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD, '__class_setup_teardown'),

            (TestCase.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD, 'classTearDown'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD, 'classTearDown'),

            (TestCase.EVENT_ON_RUN_CLASS_TEARDOWN_METHOD, '__setup_extra_class_teardowns'),
            (TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD, '__setup_extra_class_teardowns'),

            (TestCase.EVENT_ON_COMPLETE_TEST_CASE, 'run'),
        ])


class FailingTeardownMethodsTest(TestCase):

    class ClassWithTwoFailingTeardownMethods(TestCase):

        methods_ran = []

        def test_method(self):
            self.methods_ran.append("test_method")
            assert False

        @teardown
        def first_teardown(self):
            self.methods_ran.append("first_teardown")
            assert False

        @teardown
        def second_teardown(self):
            self.methods_ran.append("second_teardown")
            assert False

    @setup
    def run_test_case(self):
        self.testcase = self.ClassWithTwoFailingTeardownMethods()
        self.testcase.run()

    def test_class_with_two_failing_teardown_methods(self):
        assert_in("test_method", self.testcase.methods_ran)
        assert_in("first_teardown", self.testcase.methods_ran)
        assert_in("second_teardown", self.testcase.methods_ran)

    def test_multiple_error_formatting(self):
        test_result = self.testcase.results()[0]
        actual = test_result.format_exception_info()
        expected_regex = r"""Traceback \(most recent call last\):
  File \".*test\/test_case_test.py\", line \d+, in test_method
    assert False
AssertionError

During handling of the above exception, another exception occurred:

Traceback \(most recent call last\):
  File \".*test\/test_case_test.py\", line \d+, in first_teardown
    assert False
AssertionError

During handling of the above exception, another exception occurred:

Traceback \(most recent call last\):
  File \".*test\/test_case_test.py\", line \d+, in second_teardown
    assert False
AssertionError
"""
        assert_equal(RegexMatcher(expected_regex), actual)


class RegexMatcher(object):
    def __init__(self, regex):
        import re
        self.__re = re.compile(regex)

    def __eq__(self, other):
        return bool(self.__re.match(other))

    def __repr__(self):
        return '%s(%r)' % (
            type(self).__name__,
            self.__re.pattern,
        )


class ExceptionDuringClassSetupTest(TestCase):

    class FakeParentTestCase(TestCase):

        def __init__(self, *args, **kwargs):
            self.run_methods = []
            super(ExceptionDuringClassSetupTest.FakeParentTestCase, self).__init__(*args, **kwargs)

        @class_setup
        def parent_class_setup(self):
            self.run_methods.append("parent class_setup")
            raise Exception

        @class_teardown
        def parent_class_teardown(self):
            self.run_methods.append("parent class_teardown")

        @setup
        def parent_setup(self):
            self.run_methods.append("parent setup")
            raise Exception

        @teardown
        def parent_teardown(self):
            self.run_methods.append("parent teardown")

        def test_parent(self):
            self.run_methods.append("parent test method")

    class FakeChildTestCase(FakeParentTestCase):

        @class_setup
        def child_class_setup(self):
            self.run_methods.append("child class_setup")

        @class_teardown
        def child_class_teardown(self):
            self.run_methods.append("child class_teardown")

        @setup
        def child_setup(self):
            self.run_methods.append("child setup")

        @teardown
        def child_teardown(self):
            self.run_methods.append("child teardown")

        def test_child(self):
            self.run_methods.append("child test method")

    def test_parent(self):
        test_case = self.FakeParentTestCase()
        test_case.run()
        expected = ["parent class_setup", "parent class_teardown", ]
        assert_equal(expected, test_case.run_methods)

    def test_child(self):
        test_case = self.FakeChildTestCase()
        test_case.run()
        expected = ["parent class_setup", "child class_teardown", "parent class_teardown", ]
        assert_equal(expected, test_case.run_methods)


class ExceptionDuringSetupTest(TestCase):

    class FakeParentTestCase(TestCase):

        def __init__(self, *args, **kwargs):
            self.run_methods = []
            super(ExceptionDuringSetupTest.FakeParentTestCase, self).__init__(*args, **kwargs)

        @setup
        def parent_setup(self):
            self.run_methods.append("parent setup")
            raise Exception

        @teardown
        def parent_teardown(self):
            self.run_methods.append("parent teardown")

        def test_parent(self):
            self.run_methods.append("parent test method")

    class FakeChildTestCase(FakeParentTestCase):

        @setup
        def child_setup(self):
            self.run_methods.append("child setup")

        @teardown
        def child_teardown(self):
            self.run_methods.append("child teardown")

        def test_child(self):
            self.run_methods.append("child test method")

    def test_parent(self):
        test_case = self.FakeParentTestCase()
        test_case.run()
        expected = ["parent setup", "parent teardown", ]
        assert_equal(expected, test_case.run_methods)

    def test_child(self):
        test_case = self.FakeChildTestCase()
        test_case.run()
        # FakeChildTestCase has two test methods (test_parent and test_child), so the fixtures are run twice.
        expected = ["parent setup", "child teardown", "parent teardown", ] * 2
        assert_equal(expected, test_case.run_methods)


class ExceptionDuringClassTeardownTest(TestCase):

    class FakeParentTestCase(TestCase):

        def __init__(self, *args, **kwargs):
            self.run_methods = []
            super(ExceptionDuringClassTeardownTest.FakeParentTestCase, self).__init__(*args, **kwargs)

        @class_setup
        def parent_setup(self):
            self.run_methods.append("parent class_setup")

        @class_teardown
        def parent_teardown(self):
            self.run_methods.append("parent class_teardown")
            raise Exception

        def test_parent(self):
            self.run_methods.append("parent test method")

    class FakeChildTestCase(FakeParentTestCase):

        @class_setup
        def child_setup(self):
            self.run_methods.append("child class_setup")

        @class_teardown
        def child_teardown(self):
            self.run_methods.append("child class_teardown")

        def test_child(self):
            self.run_methods.append("child test method")

    def test_parent(self):
        test_case = self.FakeParentTestCase()
        test_case.run()
        expected = ["parent class_setup", "parent test method", "parent class_teardown", ]
        assert_equal(expected, test_case.run_methods)

    def test_child(self):
        test_case = self.FakeChildTestCase()
        test_case.run()
        expected = [
            "parent class_setup",
            "child class_setup",
            "child test method",
            "parent test method",
            "child class_teardown",
            "parent class_teardown",
        ]
        assert_equal(expected, test_case.run_methods)


class ExceptionDuringTeardownTest(TestCase):

    class FakeParentTestCase(TestCase):

        def __init__(self, *args, **kwargs):
            self.run_methods = []
            super(ExceptionDuringTeardownTest.FakeParentTestCase, self).__init__(*args, **kwargs)

        @setup
        def parent_setup(self):
            self.run_methods.append("parent setup")

        @teardown
        def parent_teardown(self):
            self.run_methods.append("parent teardown")
            raise Exception

        def test_parent(self):
            self.run_methods.append("parent test method")

    class FakeChildTestCase(FakeParentTestCase):

        @setup
        def child_setup(self):
            self.run_methods.append("child setup")

        @teardown
        def child_teardown(self):
            self.run_methods.append("child teardown")

        def test_child(self):
            self.run_methods.append("child test method")

    def test_parent(self):
        test_case = self.FakeParentTestCase()
        test_case.run()
        expected = ["parent setup", "parent test method", "parent teardown", ]
        assert_equal(expected, test_case.run_methods)

    def test_child(self):
        test_case = self.FakeChildTestCase()
        test_case.run()
        expected = [
            # Fixtures run before and after each test method.
            # Here's test_child.
            "parent setup",
            "child setup",
            "child test method",
            "child teardown",
            "parent teardown",
            # Here's test_parent.
            "parent setup",
            "child setup",
            "parent test method",
            "child teardown",
            "parent teardown",
        ]
        assert_equal(expected, test_case.run_methods)


class TestCaseKeepsReferenceToResultsForTestMethod(TestCase):
    def test_reference_to_results(self):
        assert self.test_result


class NoAttributesNamedTest(TestCase):
    class FakeTestCase(TestCase):
        def test_your_might(self):
            assert True

    def test_attributes(self):
        test_case = self.FakeTestCase()
        expected_attributes = sorted([
            "test_result",     # Part of the public API (its name is unfortunate but e.g. Selenium relies on it)
            "test_your_might",  # "Actual" test method in the test case
        ])
        actual_attributes = sorted([attribute for attribute in dir(test_case) if attribute.startswith("test")])
        assert_equal(expected_attributes, actual_attributes)


class AdhocTeardownsGetCalledTest(TestCase):

    def test_addfinalizer(self):
        class_setup_mock = mock.MagicMock()
        test_setup_mock = mock.MagicMock()
        test_mock = mock.MagicMock()
        test_teardown_mock = mock.MagicMock()
        class_teardown_mock = mock.MagicMock()

        class InnerTestCase(TestCase):

            @class_setup
            def _setup_class_mocks(self):
                self.addfinalizer(class_setup_mock)

            @setup
            def _setup_test_mock(self):
                self.addfinalizer(test_setup_mock)

            def test_things(self):
                self.addfinalizer(test_mock)
                assert not class_setup_mock.called
                assert not test_setup_mock.called
                assert not test_mock.called

            @teardown
            def _test_teardown(self):
                self.addfinalizer(test_teardown_mock)
                # The test instance teardowns run at the end of the test
                assert not class_setup_mock.called
                assert not test_setup_mock.called
                assert not test_mock.called
                assert not test_teardown_mock.called

            @class_teardown
            def _test_class_teardown(self):
                self.addfinalizer(class_teardown_mock)
                # The class teardowns run at the end of the tests
                assert not class_setup_mock.called
                assert not class_teardown_mock.called
                assert_equal(test_setup_mock.call_count, 1)
                assert_equal(test_mock.call_count, 1)
                assert_equal(test_teardown_mock.call_count, 1)

        test_case = InnerTestCase()
        test_case.run()
        assert_equal(test_case.results()[0].format_exception_info(), None)
        assert_equal(test_setup_mock.call_count, 1)
        assert_equal(test_mock.call_count, 1)
        assert_equal(test_teardown_mock.call_count, 1)
        assert_equal(class_setup_mock.call_count, 1)
        assert_equal(class_teardown_mock.call_count, 1)

    def test_multiple_tests(self):
        class_setup_mock = mock.MagicMock()
        test_setup_mock = mock.MagicMock()
        test_mock_1 = mock.MagicMock()
        test_mock_2 = mock.MagicMock()
        test_teardown_mock = mock.MagicMock()
        class_teardown_mock = mock.MagicMock()

        class InnerTestCase(TestCase):

            @class_setup
            def _setup_class_mocks(self):
                self.addfinalizer(class_setup_mock)

            @setup
            def _setup_test_mock(self):
                self.addfinalizer(test_setup_mock)

            def test_1(self):
                self.addfinalizer(test_mock_1)
                assert not class_setup_mock.called
                assert not test_setup_mock.called
                assert not test_mock_1.called
                assert not test_mock_2.called

            def test_2(self):
                self.addfinalizer(test_mock_2)
                assert_equal(test_mock_1.call_count, 1)
                assert not class_setup_mock.called
                assert not test_setup_mock.called
                assert not test_mock_2.called

            @teardown
            def _test_teardown(self):
                self.addfinalizer(test_teardown_mock)
                assert not class_setup_mock.called

            @class_teardown
            def _test_class_teardown(self):
                self.addfinalizer(class_teardown_mock)
                assert not class_setup_mock.called
                assert not class_teardown_mock.called
                assert_equal(test_setup_mock.call_count, 2)
                assert_equal(test_mock_1.call_count, 1)
                assert_equal(test_mock_2.call_count, 1)
                assert_equal(test_teardown_mock.call_count, 2)

        test_case = InnerTestCase()
        test_case.run()
        assert_equal(test_case.results()[0].format_exception_info(), None)
        assert_equal(test_setup_mock.call_count, 2)
        assert_equal(test_teardown_mock.call_count, 2)
        assert_equal(class_setup_mock.call_count, 1)
        assert_equal(class_teardown_mock.call_count, 1)
        assert_equal(test_mock_1.call_count, 1)
        assert_equal(test_mock_2.call_count, 1)

    def test_individual_test_teardowns_ordering(self):
        mock_1 = mock.MagicMock()
        mock_2 = mock.MagicMock()

        def finalizer_1():
            assert not mock_1.called
            assert mock_2.called
            mock_1()

        def finalizer_2():
            assert not mock_1.called
            assert not mock_2.called
            mock_2()

        class InnerTestCase(TestCase):

            def test_things(self):
                self.addfinalizer(finalizer_1)
                self.addfinalizer(finalizer_2)

        test_case = InnerTestCase()
        test_case.run()
        assert_equal(test_case.results()[0].format_exception_info(), None)
        assert_equal(mock_1.call_count, 1)
        assert_equal(mock_2.call_count, 1)

    def test_class_teardowns_ordering(self):
        mock_1 = mock.MagicMock()
        mock_2 = mock.MagicMock()

        def finalizer_1():
            assert not mock_1.called
            assert mock_2.called
            mock_1()

        def finalizer_2():
            assert not mock_1.called
            assert not mock_2.called
            mock_2()

        class InnerTestCase(TestCase):

            @class_setup
            def _class_setup(self):
                self.addfinalizer(finalizer_1)
                self.addfinalizer(finalizer_2)

            def test_things(self):
                pass

        test_case = InnerTestCase()
        test_case.run()
        assert_equal(test_case.results()[0].format_exception_info(), None)
        assert_equal(mock_1.call_count, 1)
        assert_equal(mock_2.call_count, 1)


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
