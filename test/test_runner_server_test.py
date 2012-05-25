import threading
import tornado.ioloop

from testify import test_case, test_runner_server, class_setup, assert_equal, setup_teardown, test_reporter, class_setup_teardown


class Struct:
    """A convenient way to make an object with some members."""
    def __init__(self, **entries):
        self.__dict__.update(entries)


class TestRunnerServerTestCase(test_case.TestCase):
    @class_setup
    def build_test_case(self):
        class DummyTestCase(test_case.TestCase):
            def __init__(self_, *args, **kwargs):
                super(DummyTestCase, self_).__init__(*args, **kwargs)
                self_.should_pass = kwargs.pop('should_pass', True)

            @class_setup_teardown
            def dummy_setup_teardown(self):
                yield

            def test(self_):
                assert self_.should_pass

        self.dummy_test_case = DummyTestCase

    @setup_teardown
    def run_server(self):
        self.reported_results = {
            'test' : [],
            'class_setup' : [],
            'class_teardown' : [],
        }

        class ResultRecorder(test_reporter.TestReporter):
            def test_complete(reporter, result):
                self.reported_results['test'].append(result)

            def class_setup_complete(reporter, result):
                self.reported_results['class_setup'].append(result)

            def class_teardown_complete(reporter, result):
                self.reported_results['class_teardown'].append(result)

        self.server = test_runner_server.TestRunnerServer(
            self.dummy_test_case,
            options=Struct(
                runner_timeout=1,
                server_timeout=10,
                revision=None,
                shutdown_delay_for_connection_close=0.001,
                shutdown_delay_for_outstanding_runners=1,
            ),
            serve_port=0,
            test_reporters=[ResultRecorder(None)],
            plugin_modules=[],
        )

        thread = threading.Thread(None, self.server.run)
        thread.start()

        yield

        self.server.shutdown()
        thread.join()

    def get_test(self, runner_id):
        """A blocking function to request a test from a TestRunnerServer."""
        sem = threading.Semaphore(0)
        tests_received = []  # Python closures aren't as cool as JS closures, so we have to use something already on the heap in order to pass data from an inner func to an outer func.

        def inner(test_dict):
            tests_received.append(test_dict)
            sem.release()

        def inner_empty():
            tests_received.append(None)
            sem.release()

        self.server.get_next_test(runner_id, inner, inner_empty)
        sem.acquire()

        (test_received,) = tests_received
        return test_received

    def timeout_class(self, runner, test):
        assert test
        sem = threading.Semaphore(0)

        def inner():
            self.server.check_in_class(runner, test['class_path'], timed_out=True)
            sem.release()

        tornado.ioloop.IOLoop.instance().add_callback(inner)
        sem.acquire()  # block until inner is finished.

    def run_test(self, runner_id, should_pass=True):
        test_instance = self.dummy_test_case(should_pass=should_pass)
        for event in (test_case.TestCase.EVENT_ON_COMPLETE_CLASS_SETUP_METHOD, test_case.TestCase.EVENT_ON_COMPLETE_TEST_METHOD, test_case.TestCase.EVENT_ON_COMPLETE_CLASS_TEARDOWN_METHOD,):
            test_instance.register_callback(
                event,
                lambda result: self.server.report_result(runner_id, result)
            )
        test_instance.run()

    def test_passing_tests_run_only_once(self):
        """Start a server with one test case to run. Make sure it hands out that test, report it as success, then make sure it gives us nothing else."""
        first_test = self.get_test('runner1')

        assert_equal(first_test['class_path'], 'test.test_runner_server_test DummyTestCase')
        assert_equal(first_test['test_methods'], ['test'])

        self.run_test('runner1')

        second_test = self.get_test('runner1')
        assert_equal(second_test, None)

    def test_requeue_on_failure(self):
        """Start a server with one test case to run. Make sure it hands out that test, report it as failure, then make sure it gives us the same one, then nothing else."""
        first_test = self.get_test('runner1')
        assert_equal(first_test['class_path'], 'test.test_runner_server_test DummyTestCase')
        assert_equal(first_test['test_methods'], ['test'])

        self.run_test('runner1', should_pass=False)

        second_test = self.get_test('runner2')
        assert_equal(second_test['class_path'], 'test.test_runner_server_test DummyTestCase')
        assert_equal(second_test['test_methods'], ['test'])

        self.run_test('runner2', should_pass=False)

        assert_equal(self.get_test('runner3'), None)

    def test_requeue_on_timeout(self):
        """Start a server with one test case to run. Make sure it hands out the same test twice, then nothing else."""

        first_test = self.get_test('runner1')
        self.timeout_class('runner1', first_test)

        # Now just ask for a second test. This should give us the same test again.
        second_test = self.get_test('runner2')
        self.timeout_class('runner2', second_test)

        # Ask for a third test. This should give us None.
        third_test = self.get_test('runner3')

        assert first_test
        assert second_test

        assert_equal(first_test['class_path'], second_test['class_path'])
        assert_equal(first_test['test_methods'], second_test['test_methods'])
        assert_equal(third_test, None)

    def test_fail_then_timeout_twice(self):
        """Fail, then time out, then time out again, then time out again.
        The first three fetches should give the same test; the last one should be None."""
        first_test = self.get_test('runner1')
        self.run_test('runner1', should_pass=False)

        second_test = self.get_test('runner2')
        self.timeout_class('runner2', second_test)

        third_test = self.get_test('runner3')
        self.timeout_class('runner3', third_test)

        assert_equal(first_test['class_path'], second_test['class_path'])
        assert_equal(first_test['test_methods'], second_test['test_methods'])

        assert_equal(first_test['class_path'], third_test['class_path'])
        assert_equal(first_test['test_methods'], third_test['test_methods'])

        # Check that it didn't requeue again.
        assert_equal(self.get_test('runner4'), None)

    def test_timeout_then_fail_twice(self):
        """Time out once, then fail, then fail again.
        The first three fetches should give the same test; the last one should be None."""
        first_test = self.get_test('runner1')
        self.timeout_class('runner1', first_test)

        # Don't run it.
        second_test = self.get_test('runner2')
        self.run_test('runner2', should_pass=False)
        third_test = self.get_test('runner3')
        self.run_test('runner3', should_pass=False)
        assert_equal(first_test['class_path'], second_test['class_path'])
        assert_equal(first_test['test_methods'], second_test['test_methods'])
        assert_equal(first_test['class_path'], third_test['class_path'])
        assert_equal(first_test['test_methods'], third_test['test_methods'])

        # Check that it didn't requeue again.
        assert_equal(self.get_test('runner4'), None)

    def test_tests_and_fixtures_reported_pass(self):
        """Test that when everything passes, the server reports results."""
        first_test = self.get_test('runner1')
        self.run_test('runner1', should_pass=True)

        class_setup_results = self.reported_results['class_setup']
        test_result, = self.reported_results['test']
        class_teardown_results = self.reported_results['class_teardown']

        assert_equal(sorted([csr['method']['name'] for csr in class_setup_results]), sorted([
            'classSetUp',
            'dummy_setup_teardown',
        ]))
        assert_equal(test_result['method']['name'], 'test')
        assert_equal(sorted([ctr['method']['name'] for ctr in class_teardown_results]), sorted([
            'dummy_setup_teardown',
            'classTearDown',
        ]))

    def test_tests_and_fixtures_reported_timeout(self):
        """If a class times out, there should be a fake result for everything."""
        first_test = self.get_test('runner1')
        self.timeout_class('runner1', first_test)
        second_test = self.get_test('runner2')
        self.timeout_class('runner2', second_test)

        class_setup_results = self.reported_results['class_setup']
        test_result, = self.reported_results['test']
        class_teardown_results = self.reported_results['class_teardown']

        assert_equal(sorted([csr['method']['name'] for csr in class_setup_results]), sorted([
            'dummy_setup_teardown',
            'dummy_setup_teardown',
            'classSetUp',
            'classSetUp',
        ]))
        assert_equal(test_result['method']['name'], 'test')
        assert_equal(sorted([ctr['method']['name'] for ctr in class_teardown_results]), sorted([
            'dummy_setup_teardown',
            'dummy_setup_teardown',
            'classTearDown',
            'classTearDown',
        ]))

        for result in class_setup_results + class_teardown_results + [test_result]:
            assert result['error']


class AsyncQueueTestCase(test_case.TestCase):
    def test_preserves_ordering(self):
        """If we put in several things with the same priority, they should come out FIFO"""
        q = test_runner_server.AsyncQueue()

        expected_values = [
            (0, "a"),
            (0, "c"),
            (0, "b"),
        ]

        for priority, data in expected_values:
            q.put(priority, data)

        def check_data(priority, data):
            expected_priority, expected_data = expected_values[0]
            expected_values[0:1] = []

            assert_equal(priority, expected_priority)
            assert_equal(data, expected_data)

        for _ in xrange(len(expected_values)):
            q.get(0, check_data)
