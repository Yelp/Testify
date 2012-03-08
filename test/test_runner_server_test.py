import threading
import time

from testify import test_case, test_runner_server, setup, class_setup, assert_equal

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
			def test(self_):
				pass
		self.dummy_test_case = DummyTestCase

	def test_requeue_on_timeout(self):
		"""Start a server with one test case to run. Make sure it hands out the same test twice, then nothing else."""
		server = test_runner_server.TestRunnerServer(
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

		with ThreadContext(server.run, server.shutdown):
			first_test = get_test(server, 'runner1')
			second_test = get_test(server, 'runner2')
			third_test = get_test(server, 'runner3')

			assert_equal(first_test['class_path'], second_test['class_path'])
			assert_equal(first_test['methods'], second_test['methods'])
			assert_equal(third_test, None)