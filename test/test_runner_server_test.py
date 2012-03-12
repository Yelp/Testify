import threading
import tornado.ioloop

from testify import test_case, test_runner_server, setup, class_setup, assert_equal, test_result

class Struct:
    """A convenient way to make an object with some members."""
    def __init__(self, **entries):
        self.__dict__.update(entries)

class ThreadContext(object):
    """Run func in another thread, calling cleanup_func (which should be something that causes func to return) once the with-block finishes."""
    def __init__(self, func, cleanup_func=lambda:None):
        self.cleanup_func = cleanup_func
        self.thread = threading.Thread(None, func)

    def __enter__(self):
        self.thread.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup_func()
        self.thread.join()

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

    (test_received,) = tests_received
    return test_received

class TestRunnerServerTestCase(test_case.TestCase):
    @class_setup
    def build_test_case(self):
        class DummyTestCase(test_case.TestCase):
            def __init__(self_, *args, **kwargs):
                super(DummyTestCase, self_).__init__(*args, **kwargs)
                self_.should_pass = kwargs.pop('should_pass', True)
            def test(self_):
                assert self_.should_pass

        self.dummy_test_case = DummyTestCase

    @setup
    def build_server(self):
        self.server = test_runner_server.TestRunnerServer(
            self.dummy_test_case,
            options=Struct(
                runner_timeout=0.01,
                server_timeout=1,
                revision=None,
            ),
            serve_port=0,
            test_reporters=[],
            plugin_modules=[],
        );

    def run_test(self, runner_id, should_pass=True):
        test_instance = self.dummy_test_case(should_pass=should_pass)
        test_instance.register_callback(
            test_case.TestCase.EVENT_ON_COMPLETE_TEST_METHOD,
            lambda result: self.server.report_result(runner_id, result)
        )
        test_instance.run()

    def test_passing_tests_run_only_once(self):
        """Start a server with one test case to run. Make sure it hands out that test, report it as success, then make sure it gives us nothing else."""
        with ThreadContext(self.server.run, self.server.shutdown):
            first_test = get_test(self.server, 'runner1')

            assert_equal(first_test['class_path'], 'test.test_runner_server_test DummyTestCase')
            assert_equal(first_test['methods'], ['test'])

            self.run_test('runner1')

            second_test = get_test(self.server, 'runner1')
            assert_equal(second_test, None)

    def test_requeue_on_failure(self):
        """Start a server with one test case to run. Make sure it hands out that test, report it as failure, then make sure it gives us the same one, then nothing else."""
        with ThreadContext(self.server.run, self.server.shutdown):
            first_test = get_test(self.server, 'runner1')
            assert_equal(first_test['class_path'], 'test.test_runner_server_test DummyTestCase')
            assert_equal(first_test['methods'], ['test'])

            self.run_test('runner1', should_pass=False)

            second_test = get_test(self.server, 'runner2')
            assert_equal(second_test['class_path'], 'test.test_runner_server_test DummyTestCase')
            assert_equal(second_test['methods'], ['test'])

            self.run_test('runner2', should_pass=False)

            assert_equal(get_test(self.server, 'runner3'), None)

    def test_requeue_on_timeout(self):
        """Start a server with one test case to run. Make sure it hands out the same test twice, then nothing else."""

        with ThreadContext(self.server.run, self.server.shutdown):
            first_test = get_test(self.server, 'runner1')
            # Now just ask for a second test. This will wait 0.01 seconds (the timeout) before giving us the same test again.
            second_test = get_test(self.server, 'runner2')
            # Ask for a third test. This again will wait 0.01 seconds before giving us None.
            third_test = get_test(self.server, 'runner3')

            assert first_test
            assert second_test

            assert_equal(first_test['class_path'], second_test['class_path'])
            assert_equal(first_test['methods'], second_test['methods'])
            assert_equal(third_test, None)

    def test_fail_then_timeout_twice(self):
        """Fail, then time out, then time out again, then time out again.
        The first three fetches should give the same test; the last one should be None."""
        with ThreadContext(self.server.run, self.server.shutdown):
            first_test = get_test(self.server, 'runner1')
            self.run_test('runner1', should_pass=False)

            second_test = get_test(self.server, 'runner2')
            # Don't run it.

            third_test = get_test(self.server, 'runner3')
            self.run_test('runner3', should_pass=False)

            assert_equal(first_test['class_path'], second_test['class_path'])
            assert_equal(first_test['methods'], second_test['methods'])

            assert_equal(first_test['class_path'], third_test['class_path'])
            assert_equal(first_test['methods'], third_test['methods'])

            # Check that it didn't requeue again.
            assert_equal(get_test(self.server, 'runner4'), None)

    def test_timeout_then_fail_twice(self):
        """Time out once, then fail, then fail again.
        The first three fetches should give the same test; the last one should be None."""
        with ThreadContext(self.server.run, self.server.shutdown):
            first_test = get_test(self.server, 'runner1')
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