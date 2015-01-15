import imp
import mock
from testify import assert_equal
from testify import setup
from testify import setup_teardown
from testify import test_case
from testify import test_discovery
from testify import test_runner

import six

from .test_runner_subdir.inheriting_class import InheritingClass
from .test_runner_bucketing import bucketing_test

prepared = False
running = False


def prepare_test_case(options, test_case):
    global prepared
    prepared = True


def run_test_case(options, test_case, runnable):
    global running
    running = True
    try:
        return runnable()
    finally:
        running = False


def add_testcase_info(test_case, runner):
    test_case.__testattr__ = True


class TestTestRunnerGetTestMethodName(test_case.TestCase):

    def test_method_from_other_module_reports_class_module(self):
        ret = test_runner.TestRunner.get_test_method_name(
            InheritingClass().test_foo,
        )

        assert_equal(
            ret,
            '{0} {1}.{2}'.format(
                InheritingClass.__module__,
                InheritingClass.__name__,
                InheritingClass.test_foo.__name__,
            ),
        )


class PluginTestCase(test_case.TestCase):
    """Verify plugin support

    This is pretty complex and deserves some amount of explanation.
    What we're doing here is creating a module object on the fly (our plugin) and a
    test case class so we can call runner directly and verify the right parts get called.

    If you have a failure in here the stack is going to look crazy because we are a test case, being called by
    a test running, which is building and running ANOTHER test runner to execute ANOTHER test case. Cheers.
    """
    @setup
    def build_module(self):
        self.our_module = imp.new_module("our_module")
        setattr(self.our_module, "prepare_test_case", prepare_test_case)
        setattr(self.our_module, "run_test_case", run_test_case)
        setattr(self.our_module, "add_testcase_info", add_testcase_info)

    @setup
    def build_test_case(self):
        self.ran_test = False

        class DummyTestCase(test_case.TestCase):
            def test(self_):
                self.ran_test = True
                assert self.our_module.prepared
                assert self.our_module.running
                assert self.__testattr__

        self.dummy_test_class = DummyTestCase

    def test_plugin_run(self):
        runner = test_runner.TestRunner(self.dummy_test_class, plugin_modules=[self.our_module])

        assert runner.run()
        assert self.ran_test
        assert not running
        assert prepared


class TestTestRunnerGetTestsForSuite(test_case.TestCase):

    @setup_teardown
    def mock_out_things(self):
        mock_returned_test = mock.Mock()
        self.mock_test_method = mock.Mock()
        mock_returned_test.runnable_test_methods.return_value = [
            self.mock_test_method,
        ]
        with mock.patch.object(
            test_runner.TestRunner,
            'discover',
            autospec=True,
            return_value=[mock_returned_test],
        ) as self.discover_mock:
            with mock.patch.object(
                    test_case.TestCase,
                    'in_suite',
            ) as self.in_suite_mock:
                yield

    def test_get_tests_for_suite_in_suite(self):
        self.in_suite_mock.return_value = True

        instance = test_runner.TestRunner(mock.sentinel.test_class)
        ret = instance.get_tests_for_suite(mock.sentinel.selected_suite_name)
        assert_equal(ret, [self.mock_test_method])

    def test_get_tests_for_suite_not_in_suite(self):
        self.in_suite_mock.return_value = False

        instance = test_runner.TestRunner(mock.sentinel.test_class)
        ret = instance.get_tests_for_suite(mock.sentinel.selected_suite_name)
        assert_equal(ret, [])


class TestTestRunnerPrintsTestNames(test_case.TestCase):

    @setup_teardown
    def mock_out_things(self):
        class OrderableMock(mock.Mock):
            def __lt__(self, other):
                return id(self) < id(other)

        with mock.patch.object(
            test_runner.TestRunner,
            'get_tests_for_suite',
            autospec=True,
            return_value=[mock.sentinel.test1, mock.sentinel.test2],
        ) as self.get_tests_for_suite_mock:
            with mock.patch.object(
                test_runner.TestRunner,
                'get_test_method_name',
                return_value=OrderableMock(),
            ) as self.get_test_method_name_mock:
                with mock.patch.object(
                    six.moves.builtins,
                    'print',
                ) as self.print_mock:
                    yield

    def test_prints_one_per_line(self):
        instance = test_runner.TestRunner(mock.sentinel.test_class)
        instance.list_tests(mock.sentinel.selected_suite_name)
        self.print_mock.assert_has_calls([
            mock.call(self.get_test_method_name_mock.return_value)
            for _ in self.get_tests_for_suite_mock.return_value
        ])


class TestMoreFairBucketing(test_case.TestCase):
    """This tests the "more fair bucketing" approach to bucketing tests.

    The algorithm for bucketing tests is as follows:

    - If there is no bucketing, don't sort or bucket
    - Otherwise bucket as follows:

        1. Sort the tests, first by number of tests and then by name
           (Sorting by name is merely for determinism)
        2. In order, round robin associate the tests with a bucket
           following this pattern:

           (for example 3 buckets)
           1 2 3 3 2 1 1 2 3 (etc.)
    """

    all_tests = (
        bucketing_test.TestCaseWithManyTests,
        bucketing_test.TestCaseWithFewTests,
        bucketing_test.AAA_FirstTestCaseWithSameNumberOfTests,
        bucketing_test.ZZZ_SecondTestCaseWithSameNumberOfTests,
    )

    all_tests_sorted_by_number_of_tests = (
        all_tests[0],
        all_tests[2],
        all_tests[3],
        all_tests[1],
    )

    @setup_teardown
    def mock_out_test_discovery(self):
        with mock.patch.object(
            test_discovery,
            'discover',
            autospec=True,
        ) as self.discover_mock:
            yield

    def assert_types_of_discovered(self, discovered, expected):
        assert_equal(tuple(map(type, discovered)), tuple(expected))

    def test_bucketing_no_buckets(self):
        self.discover_mock.return_value = self.all_tests

        instance = test_runner.TestRunner(mock.sentinel.test_path)
        discovered = instance.discover()
        # The tests we discover should be in the order that test_discovery
        # returns them as
        self.assert_types_of_discovered(discovered, self.all_tests)

    def test_bucketing_one_bucket(self):
        """Trivial base case, should return similar to no_buckets, but with sorting"""
        self.discover_mock.return_value = self.all_tests

        instance = test_runner.TestRunner(mock.sentinel.test_path, bucket=0, bucket_count=1)
        discovered = instance.discover()
        self.assert_types_of_discovered(discovered, self.all_tests_sorted_by_number_of_tests)

    def test_multiple_buckets(self):
        self.discover_mock.return_value = self.all_tests

        # Buckets should be assigned:
        # 0 -> TestCaseWithManyTesets, TestCaseWithFewTests
        # 1 -> AAA_FirstTestCaseWithSameNumberOfTests, ZZZ_SecondTestCaseWithSameNumberOfTests
        instance = test_runner.TestRunner(mock.sentinel.test_path, bucket=0, bucket_count=2)
        discovered = instance.discover()
        self.assert_types_of_discovered(
            discovered,
            (
                bucketing_test.TestCaseWithManyTests,
                bucketing_test.TestCaseWithFewTests,
            ),
        )

        instance = test_runner.TestRunner(mock.sentinel.test_path, bucket=1, bucket_count=2)
        discovered = instance.discover()
        self.assert_types_of_discovered(
            discovered,
            (
                bucketing_test.AAA_FirstTestCaseWithSameNumberOfTests,
                bucketing_test.ZZZ_SecondTestCaseWithSameNumberOfTests,
            ),
        )

    def test_bucketing_with_filtering(self):
        self.discover_mock.return_value = self.all_tests
        instance = test_runner.TestRunner(
            mock.sentinel.test_path,
            bucket=0,
            bucket_count=1,
            module_method_overrides={
                self.all_tests[0].__name__: set(),
            },
        )

        discovered = instance.discover()
        self.assert_types_of_discovered(discovered, (self.all_tests[0],))
