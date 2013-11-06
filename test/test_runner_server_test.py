import contextlib
import logging
import threading

import mock
import tornado.ioloop

from discovery_failure_test import BrokenImportTestCase
from test_logger_test import ExceptionInClassFixtureSampleTests
from testify import (
    assert_equal,
    assert_in,
    assert_any_match_regex,
    assert_raises_and_contains,
    class_setup,
    class_teardown,
    setup,
    teardown,
    test_case,
    test_runner_server,
    test_result,
)
from testify.utils import turtle

_log = logging.getLogger('testify')


def get_test(server, runner_id):
    """A blocking function to request a test from a TestRunnerServer."""
    sem = threading.Semaphore(0)
    tests_received = [] # Python closures aren't as cool as JS closures, so we have to use something already on the heap in order to pass data from an inner func to an outer func.

    def inner(test_dict):
        tests_received.append(test_dict)
        sem.release()

    def inner_empty():
        tests_received.append(None)
        sem.release()

    server.get_next_test(runner_id, inner, inner_empty)
    sem.acquire()

    # Verify only one test was received.
    (test_received,) = tests_received
    return test_received


@contextlib.contextmanager
def disable_requeueing(server):
    orig_disable_requeueing = server.disable_requeueing
    server.disable_requeueing = True
    yield
    server.disable_requeueing = orig_disable_requeueing


class TestRunnerServerBaseTestCase(test_case.TestCase):
    __test__ = False

    def build_test_case(self):
        class DummyTestCase(test_case.TestCase):
            def __init__(self_, *args, **kwargs):
                super(DummyTestCase, self_).__init__(*args, **kwargs)
                self_.should_pass = kwargs.pop('should_pass', True)
            def test(self_):
                assert self_.should_pass

        self.dummy_test_case = DummyTestCase

    def run_test(self, runner_id, should_pass=True):
        self.test_instance = self.dummy_test_case(should_pass=should_pass)
        for event in [
            test_case.TestCase.EVENT_ON_COMPLETE_TEST_METHOD,
            test_case.TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD,
            test_case.TestCase.EVENT_ON_COMPLETE_TEST_CASE,
        ]:
            self.test_instance.register_callback(
                event,
                lambda result: self.server.report_result(runner_id, result),
            )

        self.test_instance.run()

    def get_seen_methods(self, test_complete_calls):
        seen_methods = set()
        for call in test_complete_calls:
            args = call[0]
            first_arg = args[0]
            first_method_name = first_arg['method']['name']
            seen_methods.add(first_method_name)
        return seen_methods

    def start_server(self, test_reporters=None, failure_limit=None):
        if test_reporters is None:
            self.test_reporter = turtle.Turtle()
            test_reporters = [self.test_reporter]

        self.server = test_runner_server.TestRunnerServer(
            self.dummy_test_case,
            options=turtle.Turtle(
                runner_timeout=1,
                server_timeout=10,
                revision=None,
                shutdown_delay_for_connection_close=0.001,
                shutdown_delay_for_outstanding_runners=1,
            ),
            serve_port=0,
            test_reporters=test_reporters,
            plugin_modules=[],
            failure_limit=failure_limit,
        );

        def catch_exceptions_in_thread():
            try:
                self.server.run()
            except (Exception, SystemExit), exc:
                _log.error("Thread threw exception: %r" % exc)
                raise

        self.thread = threading.Thread(None, catch_exceptions_in_thread)
        self.thread.start()

    def stop_server(self):
        self.server.shutdown()
        self.thread.join()

    @class_setup
    def setup_test_case(self):
        self.build_test_case()

    @setup
    def setup_server(self):
        self.start_server()

    @teardown
    def teardown_server(self):
        self.stop_server()


class TestRunnerServerBrokenImportTestCase(TestRunnerServerBaseTestCase, BrokenImportTestCase,):
    def create_broken_import_file(self):
        """We must control when this setup method is run since
        build_test_case() depends on it. So we'll stub it out for now and call
        it when we're ready from build_test_case()."""
        pass

    def build_test_case(self):
        super(TestRunnerServerBrokenImportTestCase, self).create_broken_import_file()
        self.dummy_test_case = self.broken_import_module

    def start_server(self):
        """To insure the server has started before we start testing, set up a
        lock which will be released when reporting happens as the final phase
        of server startup.

        Without this, weird race conditions abound where things break because
        server startup is incomplete."""
        lock = threading.Event()
        self.report_call_count = 0

        def report_releases_lock():
            lock.set()
            self.report_call_count += 1
        self.mock_reporter = turtle.Turtle(report=report_releases_lock)
        super(TestRunnerServerBrokenImportTestCase, self).start_server(test_reporters=[self.mock_reporter])

        lock.wait(1)
        assert lock.isSet(), "Timed out waiting for server to finish starting."

    def test_reports_are_generated_after_discovery_failure(self):
        assert_equal(self.report_call_count, 1)


class TestRunnerServerTestCase(TestRunnerServerBaseTestCase):
    def timeout_class(self, runner, test):
        assert test
        tornado.ioloop.IOLoop.instance().add_callback(lambda: self.server.check_in_class(runner, test['class_path'], timed_out=True))

    def test_passing_tests_run_only_once(self):
        """Start a server with one test case to run. Make sure it hands out that test, report it as success, then make sure it gives us nothing else."""
        first_test = get_test(self.server, 'runner1')

        assert_equal(first_test['class_path'], 'test.test_runner_server_test DummyTestCase')
        assert_equal(first_test['methods'], ['test', 'run'])

        self.run_test('runner1')

        second_test = get_test(self.server, 'runner1')
        assert_equal(second_test, None)

    def test_requeue_on_failure(self):
        """Start a server with one test case to run. Make sure it hands out that test, report it as failure, then make sure it gives us the same one, then nothing else."""
        first_test = get_test(self.server, 'runner1')
        assert_equal(first_test['class_path'], 'test.test_runner_server_test DummyTestCase')
        assert_equal(first_test['methods'], ['test', 'run'])

        self.run_test('runner1', should_pass=False)

        second_test = get_test(self.server, 'runner2')
        assert_equal(second_test['class_path'], 'test.test_runner_server_test DummyTestCase')
        assert_equal(second_test['methods'], ['test', 'run'])

        self.run_test('runner2', should_pass=False)

        assert_equal(get_test(self.server, 'runner3'), None)

    def test_requeue_on_timeout(self):
        """Start a server with one test case to run. Make sure it hands out the same test twice, then nothing else."""

        first_test = get_test(self.server, 'runner1')
        self.timeout_class('runner1', first_test)

        # Now just ask for a second test. This should give us the same test again.
        second_test = get_test(self.server, 'runner2')
        self.timeout_class('runner2', second_test)

        # Ask for a third test. This should give us None.
        third_test = get_test(self.server, 'runner3')

        assert first_test
        assert second_test

        assert_equal(first_test['class_path'], second_test['class_path'])
        assert_equal(first_test['methods'], second_test['methods'])
        assert_equal(third_test, None)

    def test_disable_requeueing_on_failure(self):
        with disable_requeueing(self.server):
            first_test = get_test(self.server, 'runner1')
            assert_equal(first_test['class_path'], 'test.test_runner_server_test DummyTestCase')
            assert_equal(first_test['methods'], ['test', 'run'])

            self.run_test('runner1', should_pass=False)

            assert_equal(get_test(self.server, 'runner2'), None)

    def test_disable_requeueing_on_timeout(self):
        with disable_requeueing(self.server):
            first_test = get_test(self.server, 'runner1')
            self.timeout_class('runner1', first_test)

            assert_equal(get_test(self.server, 'runner2'), None)

    def test_report_when_requeueing_is_disabled(self):
        with disable_requeueing(self.server):
            first_test = get_test(self.server, 'runner1')
            assert_equal(first_test['class_path'], 'test.test_runner_server_test DummyTestCase')
            assert_equal(first_test['methods'], ['test', 'run'])

            self.run_test('runner1', should_pass=False)

            test_complete_calls = self.test_reporter.test_complete.calls
            test_complete_call_args = [call[0] for call in test_complete_calls]
            test_results = [args[0] for args in test_complete_call_args]
            full_names = [tr['method']['full_name'] for tr in test_results]
            assert_any_match_regex('test.test_runner_server_test DummyTestCase.test', full_names)

    def test_fail_then_timeout_twice(self):
        """Fail, then time out, then time out again, then time out again.
        The first three fetches should give the same test; the last one should be None."""
        first_test = get_test(self.server, 'runner1')
        self.run_test('runner1', should_pass=False)

        second_test = get_test(self.server, 'runner2')
        self.timeout_class('runner2', second_test)

        third_test = get_test(self.server, 'runner3')
        self.timeout_class('runner3', third_test)


        assert_equal(first_test['class_path'], second_test['class_path'])
        assert_equal(first_test['methods'], second_test['methods'])

        assert_equal(first_test['class_path'], third_test['class_path'])
        assert_equal(first_test['methods'], third_test['methods'])

        # Check that it didn't requeue again.
        assert_equal(get_test(self.server, 'runner4'), None)

    def test_timeout_then_fail_twice(self):
        """Time out once, then fail, then fail again.
        The first three fetches should give the same test; the last one should be None."""
        first_test = get_test(self.server, 'runner1')
        self.timeout_class('runner1', first_test)

        # Don't run it.
        second_test = get_test(self.server, 'runner2')
        self.run_test('runner2', should_pass=False)
        third_test = get_test(self.server, 'runner3')
        self.run_test('runner3', should_pass=False)
        assert_equal(first_test['class_path'], second_test['class_path'])
        assert_equal(first_test['methods'], second_test['methods'])
        assert_equal(first_test['class_path'], third_test['class_path'])
        assert_equal(first_test['methods'], third_test['methods'])

        # Check that it didn't requeue again.
        assert_equal(get_test(self.server, 'runner4'), None)

    def test_get_next_test_doesnt_loop_forever(self):
        """In certain situations, get_next_test will recurse until it runs out of stack space. Make sure that doesn't happen.

        Here are the conditions needed to reproduce this bug
         - The server sees multiple runners
         - The server has more than one test in its queue
         - All the tests in the server's queue were last run by the runner asking for tests.
        """
        self.server.test_queue = test_runner_server.AsyncDelayedQueue()

        self.server.test_queue.put(0, {'last_runner': 'foo', 'class_path': '1', 'methods': ['blah'], 'fixture_methods': []})
        self.server.test_queue.put(0, {'last_runner': 'foo', 'class_path': '2', 'methods': ['blah'], 'fixture_methods': []})
        self.server.test_queue.put(0, {'last_runner': 'foo', 'class_path': '3', 'methods': ['blah'], 'fixture_methods': []})

        failures = []

        def on_test_callback(test):
            failures.append("get_next_test called back with a test.")

        def on_empty_callback():
            failures.append("get_next_test called back with no test.")

        # We need the server to see multiple runners, otherwise the offending code path doesn't get triggered.
        get_test(self.server, 'bar')
        # If this test fails the way we expect it to, this call to get_test will block indefinitely.

        thread = threading.Thread(None, lambda: self.server.get_next_test('foo', on_test_callback, on_empty_callback))
        thread.start()
        thread.join(0.5)

        assert not thread.is_alive(), "get_next_test is still running after 0.5s"

        if failures:
            raise Exception(' '.join(failures))

    def test_activity_on_method_results(self):
        """Previously, the server was not resetting last_activity_time when a client posted results.
        This could lead to an issue when the last client still running tests takes longer than the
        server_timeout. See https://github.com/Yelp/Testify/issues/110
        """

        test = get_test(self.server, 'runner1')
        def make_fake_result(method):
            result = test_result.TestResult(getattr(self.dummy_test_case, method))
            result.start()
            result.end_in_success()
            return result.to_dict()

        for method in test['methods']:
            method_is_last = method == test['methods'][-1]
            if method_is_last:
                # 'activate' will be called twice at the end: once after the
                # method runs, then once more when the TestCase is checked back
                # in to the master.
                expected_call_count = 2
            else:
                expected_call_count = 1
            result = make_fake_result(method)

            with mock.patch.object(self.server, 'activity') as m_activity:
                self.server.report_result('runner1', result)
                assert_equal(m_activity.call_count, expected_call_count)

    def test_fake_result_format(self):
        get_test(self.server, 'runner1')

        fake_result = self.server._fake_result('foo', 'bar', 'baz')
        fake_result = _replace_values_with_types(fake_result)

        real_result = test_result.TestResult(self.dummy_test_case.test, runner_id='foo!')
        real_result.start()
        try:
            print 1/0
        except:
            import sys
            real_result.end_in_failure(sys.exc_info())
        real_result = real_result.to_dict()
        real_result = _replace_values_with_types(real_result)

        assert_equal(fake_result, real_result)


class TestRunnerServerExceptionInSetupPhaseBaseTestCase(TestRunnerServerBaseTestCase):
    """Child classes should set:

    - self.dummy_test_case - a test case that raises an exception during a
      class_setup or the setup phase of a class_setup_teardown

    - self.class_setup_teardown_method_name - the name of the method which will raise an
      exception

    This class's test method will do the rest.
    """

    __test__ = False

    def test_exception_in_setup_phase(self):
        """If a class_setup method raises an exception, this exception is
        reported as an error in all of the test methods in the test case. The
        methods are then treated as flakes and re-run.
        """
        # Pull and run the test case, thereby causing class_setup to run.
        test_case = get_test(self.server, 'runner')
        assert_equal(len(test_case['methods']), 3)
        # The last method will be the special 'run' method which signals the
        # entire test case is complete (including class_teardown).
        assert_equal(test_case['methods'][-1], 'run')

        self.run_test('runner')

        # 'classTearDown' is a deprecated synonym for 'class_teardown'. We
        # don't especially care about it, but it's in there.
        #
        # Exceptions during execution of class_setup cause test methods to fail
        # and get requeued as flakes. They aren't reported now because they
        # aren't complete.
        expected_methods = set(['classTearDown', 'run'])
        # self.run_test configures us up to collect results submitted at
        # class_teardown completion time. class_setup_teardown methods report
        # the result of their teardown phase at "class_teardown completion"
        # time. So, when testing the setup phase of class_setup_teardown, we
        # will see an "extra" method.
        #
        # Child classes which exercise class_setup_teardown will set
        # self.class_setup_teardown_method_name so we can add it to
        # expected_methods here.
        if hasattr(self, 'class_setup_teardown_method_name'):
            expected_methods.add(self.class_setup_teardown_method_name)
        seen_methods = self.get_seen_methods(self.test_reporter.test_complete.calls)
        # This produces a clearer diff than simply asserting the sets are
        # equal.
        assert_equal(expected_methods.symmetric_difference(seen_methods), set())

        # Verify the failed test case is re-queued for running.
        assert_equal(self.server.test_queue.empty(), False)
        requeued_test_case = get_test(self.server, 'runner2')
        assert_in(self.dummy_test_case.__name__, requeued_test_case['class_path'])

        # Reset reporter.
        self.test_reporter.test_complete = turtle.Turtle()

        # Run tests again.
        self.run_test('runner2')

        # This time, test methods have been re-run as flakes. Now that these
        # methods are are complete, they should be reported.
        expected_methods = set(['test1', 'test2', 'classTearDown', 'run'])
        if hasattr(self, 'class_setup_teardown_method_name'):
            expected_methods.add(self.class_setup_teardown_method_name)
        seen_methods = self.get_seen_methods(self.test_reporter.test_complete.calls)
        # This produces a clearer diff than simply asserting the sets are
        # equal.
        assert_equal(expected_methods.symmetric_difference(seen_methods), set())

        # Verify no more test cases have been re-queued for running.
        assert_equal(self.server.test_queue.empty(), True)

class TestRunnerServerExceptionInClassSetupTestCase(TestRunnerServerExceptionInSetupPhaseBaseTestCase):
    def build_test_case(self):
        self.dummy_test_case = ExceptionInClassFixtureSampleTests.FakeClassSetupTestCase


class TestRunnerServerExceptionInSetupPhaseOfClassSetupTeardownTestCase(TestRunnerServerExceptionInSetupPhaseBaseTestCase):
    def build_test_case(self):
        self.dummy_test_case = ExceptionInClassFixtureSampleTests.FakeSetupPhaseOfClassSetupTeardownTestCase
        self.class_setup_teardown_method_name = 'class_setup_teardown_raises_exception_in_setup_phase'


class TestRunnerServerExceptionInTeardownPhaseBaseTestCase(TestRunnerServerBaseTestCase):
    """Child classes should set:

    - self.dummy_test_case - a test case that raises an exception during a
      class_teardown or the teardown phase of a class_setup_teardown

    - self.teardown_method_name - the name of the method which will raise an
      exception

    This class's test method will do the rest.
    """

    __test__ = False

    def test_exception_in_teardown_phase(self):
        # Pull and run the test case, thereby causing class_teardown to run.
        test_case = get_test(self.server, 'runner')
        assert_equal(len(test_case['methods']), 3)
        # The last method will be the special 'run' method which signals the
        # entire test case is complete (including class_teardown).
        assert_equal(test_case['methods'][-1], 'run')

        self.run_test('runner')

        # 'classTearDown' is a deprecated synonym for 'class_teardown'. We
        # don't especially care about it, but it's in there.
        expected_methods = set(['test1', 'test2', self.teardown_method_name, 'classTearDown', 'run'])
        seen_methods = self.get_seen_methods(self.test_reporter.test_complete.calls)
        # This produces a clearer diff than simply asserting the sets are
        # equal.
        assert_equal(expected_methods.symmetric_difference(seen_methods), set())

        # Verify the failed class_teardown method is not re-queued for running
        # -- it doesn't make sense to re-run a "flaky" class_teardown.
        assert_equal(self.server.test_queue.empty(), True)


class TestRunnerServerExceptionInClassTeardownTestCase(TestRunnerServerExceptionInTeardownPhaseBaseTestCase):
    def build_test_case(self):
        self.dummy_test_case = ExceptionInClassFixtureSampleTests.FakeClassTeardownTestCase
        self.teardown_method_name = 'class_teardown_raises_exception'


class TestRunnerServerExceptionInTeardownPhaseOfClassSetupTeardownTestCase(TestRunnerServerExceptionInTeardownPhaseBaseTestCase):
    def build_test_case(self):
        self.dummy_test_case = ExceptionInClassFixtureSampleTests.FakeTeardownPhaseOfClassSetupTeardownTestCase
        self.teardown_method_name = 'class_setup_teardown_raises_exception_in_teardown_phase'


class FailureLimitTestCaseMixin(object):
    """A mixin containing dummy test cases for verifying failure limit behavior."""

    class FailureLimitTestCase(test_case.TestCase):
        """Basic test case containing test methods which fail."""
        TEST_CASE_FAILURE_LIMIT = 0

        def __init__(self, *args, **kwargs):
            test_case.TestCase.__init__(self, *args, **kwargs)
            self.failure_limit = self.TEST_CASE_FAILURE_LIMIT

        def test1(self):
            assert False, "I am the first failure. failure_limit is %s" % self.failure_limit

        def test2(self):
            assert False, "I am the second (and last) failure. failure_limit is %s" % self.failure_limit

        def test3(self):
            assert False, "This test should not run because failure_count (%s) >= failure_limit (%s)." % (self.failure_count, self.failure_limit)

    class TestCaseFailureLimitTestCase(FailureLimitTestCase):
        TEST_CASE_FAILURE_LIMIT = 2

    class FailureLimitClassTeardownFailureTestCase(FailureLimitTestCase):
        """Add failing class_teardown methods to FailureLimitTestCase."""

        CLASS_TEARDOWN_FAILURES = 2

        @class_teardown
        def teardown1(self):
            assert False, "I am the failure beyond the last failure. failure_limit is %s" % self.failure_limit

        @class_teardown
        def teardown2(self):
            assert False, "I am the second failure beyond the last failure. failure_limit is %s" % self.failure_limit

    class TestCaseFailureLimitClassTeardownFailureTestCase(FailureLimitClassTeardownFailureTestCase):
        TEST_CASE_FAILURE_LIMIT = 2

    class FailureLimitClassTeardownErrorTestCase(FailureLimitTestCase):
        """Add to FailureLimitTestCase class_teardown methods which raises exceptions."""

        CLASS_TEARDOWN_FAILURES = 2

        @class_teardown
        def teardown_1(self):
            raise Exception("I am the failure beyond the last failure. failure_limit is %s" % self.failure_limit)

        @class_teardown
        def teardown_2(self):
            raise Exception("I am the second failure beyond the last failure. failure_limit is %s" % self.failure_limit)

    class TestCaseFailureLimitClassTeardownErrorTestCase(FailureLimitClassTeardownErrorTestCase):
        TEST_CASE_FAILURE_LIMIT = 2


class TestCaseFailureLimitTestCase(TestRunnerServerBaseTestCase, FailureLimitTestCaseMixin):
    """Verify that test methods are not run after TestCase.failure_limit is
    reached.
    """

    def build_test_case(self):
        self.dummy_test_case = FailureLimitTestCaseMixin.TestCaseFailureLimitTestCase

    def test_methods_are_not_run_after_failure_limit_reached(self):
        get_test(self.server, 'runner')
        self.run_test('runner')
        # Verify that only N failing tests are run, where N is the test case's
        # failure_limit.
        assert_equal(self.test_instance.failure_count, self.dummy_test_case.TEST_CASE_FAILURE_LIMIT)


class TestCaseFailureLimitClassTeardownFailureTestCase(TestRunnerServerBaseTestCase, FailureLimitTestCaseMixin):
    """Verify that failures in class_teardown methods are counted even after
    failure_limit is reached.
    """

    def build_test_case(self):
        self.dummy_test_case = FailureLimitTestCaseMixin.TestCaseFailureLimitClassTeardownFailureTestCase

    def test_methods_are_not_run_after_failure_limit_reached(self):
        get_test(self.server, 'runner')
        self.run_test('runner')
        # Let N = the test case's failure limit
        # Let C = the number of class_teardown methods with failures
        # N failing tests will run, followed by C class_teardown methods.
        # So the test case's failure_count should be N + C.
        assert_equal(self.test_instance.failure_count, self.dummy_test_case.TEST_CASE_FAILURE_LIMIT + self.dummy_test_case.CLASS_TEARDOWN_FAILURES)


class TestCaseFailureLimitClassTeardownErrorTestCase(TestCaseFailureLimitClassTeardownFailureTestCase):
    """Verify that errors in class_teardown methods are counted even after
    failure_limit is reached.

    We modify the dummy test case to have class_teardown methods which raise
    exceptions and let the test methods from the parent class do the
    verification.
    """

    def build_test_case(self):
        self.dummy_test_case = FailureLimitTestCaseMixin.TestCaseFailureLimitClassTeardownErrorTestCase


class TestRunnerServerFailureLimitTestCase(TestRunnerServerBaseTestCase, FailureLimitTestCaseMixin):
    """Verify that test methods are not run after TestRunnerServer.failure_limit is
    reached.
    """

    TEST_RUNNER_SERVER_FAILURE_LIMIT = 2

    def build_test_case(self):
        self.dummy_test_case = FailureLimitTestCaseMixin.FailureLimitTestCase

    def start_server(self):
        """Call parent's start_server but with a failure_limit."""
        super(TestRunnerServerFailureLimitTestCase, self).start_server(failure_limit=self.TEST_RUNNER_SERVER_FAILURE_LIMIT)

    def test_methods_are_not_run_after_failure_limit_reached(self):
        assert_equal(self.server.failure_count, 0)
        get_test(self.server, 'runner')
        assert_raises_and_contains(
            ValueError,
            'FailureLimitTestCase not checked out.',
            self.run_test,
            'runner',
        )
        # Verify that only N failing tests are run, where N is the server's
        # failure_limit.
        assert_equal(self.server.failure_count, self.TEST_RUNNER_SERVER_FAILURE_LIMIT)


class TestRunnerServerFailureLimitClassTeardownFailureTestCase(TestRunnerServerBaseTestCase, FailureLimitTestCaseMixin):
    """Verify that test methods are not run after TestRunnerServer.failure_limit is
    reached, but class_teardown methods (which might continue to bump
    failure_count) are still run.
    """

    TEST_RUNNER_SERVER_FAILURE_LIMIT = 2

    def build_test_case(self):
        self.dummy_test_case = FailureLimitTestCaseMixin.FailureLimitClassTeardownFailureTestCase

    def start_server(self):
        """Call parent's start_server but with a failure_limit."""
        super(TestRunnerServerFailureLimitClassTeardownFailureTestCase, self).start_server(failure_limit=self.TEST_RUNNER_SERVER_FAILURE_LIMIT)

    def test_class_teardown_counted_as_failure_after_limit_reached(self):
        assert_equal(self.server.failure_count, 0)
        get_test(self.server, 'runner')

        # The following behavior is bad because it doesn't allow clients to
        # report class_teardown failures (which they are contractually
        # obligated to run regardless of any failure limit). See
        # https://github.com/Yelp/Testify/issues/120 for ideas about how to fix
        # this.
        #
        # For now, we write this test to pin down the existing behavior and
        # notice if it changes.
        test_case_name = self.dummy_test_case.__name__
        assert_raises_and_contains(
            ValueError,
            '%s not checked out.' % test_case_name,
            self.run_test,
            'runner',
        )
        # Verify that only N failing tests are run, where N is the server's
        # failure_limit.
        #
        # Once issue #120 is fixed, the failure count should (probably) be
        # TEST_RUNNER_SERVER_FAILURE_LIMIT + CLASS_TEARDOWN_FAILURES.
        assert_equal(self.server.failure_count, self.TEST_RUNNER_SERVER_FAILURE_LIMIT)


class TestRunnerServerFailureLimitClassTeardownErrorTestCase(TestRunnerServerFailureLimitClassTeardownFailureTestCase):
    """Verify that test methods are not run after TestRunnerServer.failure_limit is
    reached, but class_teardown methods (which might continue to bump
    failure_count) are still run.

    We modify the dummy test case to have class_teardown methods which raise
    exceptions and let the test methods from the parent class do the
    verification.
    """

    def build_test_case(self):
        self.dummy_test_case = FailureLimitTestCaseMixin.FailureLimitClassTeardownErrorTestCase

def _replace_values_with_types(obj):
    # This makes it simple to compare the format of two dictionaries.
    if isinstance(obj, dict):
        return dict((key, _replace_values_with_types(val)) for key, val in obj.items())
    else:
        return type(obj).__name__


# vim: set ts=4 sts=4 sw=4 et:
