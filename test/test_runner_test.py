import mock
from testify import assert_equal
from testify import setup
from testify import setup_teardown
from testify import test_case
from testify import test_runner
from types import ModuleType

from .test_runner_subdir.inheriting_class import InheritingClass

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
            '{} {}.{}'.format(
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
        self.our_module = ModuleType("our_module")
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

        assert runner.run() == 0
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
        assert_equal(list(ret), [self.mock_test_method])

    def test_get_tests_for_suite_not_in_suite(self):
        self.in_suite_mock.return_value = False

        instance = test_runner.TestRunner(mock.sentinel.test_class)
        ret = instance.get_tests_for_suite(mock.sentinel.selected_suite_name)
        assert_equal(list(ret), [])
