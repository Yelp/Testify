import sqlalchemy as SA
import time
from optparse import OptionParser

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json


from testify import TestCase, setup_teardown, assert_equal, assert_not_equal, assert_gt, assert_lt, assert_in_range
from testify.test_result import TestResult
from testify.test_runner import TestRunner
from testify.plugins.sql_reporter import SQLReporter, add_command_line_options, Tests, Failures, Builds, TestResults

class DummyTestCase(TestCase):
	__test__ = False
	def test_pass(self):
		pass

	def test_fail(self):
		assert False

class SQLReporterTestCase(TestCase):
	@setup_teardown
	def make_reporter(self):
		"""Make self.reporter, a SQLReporter that runs on an empty in-memory SQLite database."""
		parser = OptionParser()
		add_command_line_options(parser)
		(options, args) = parser.parse_args([
			'--reporting-db-url', 'sqlite://',
			'--sql-reporting-frequency', '0.05',
			'--build-info', json.dumps({
				'buildbot' : 1,
				'buildnumber' : 1,
				'branch' : 'a_branch_name',
				'revision' : 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
				'buildname' : 'a_build_name'
			})
		])
		create_engine_opts = {
			'poolclass' : SA.pool.StaticPool,
			'connect_args' : {'check_same_thread' : False}
		}

		self.reporter = SQLReporter(options, create_engine_opts=create_engine_opts)

		yield

		# no teardown.


	def test_integration(self):
		"""Run a runner with self.reporter as a test reporter, and verify a bunch of stuff."""
		runner = TestRunner(DummyTestCase, test_reporters=[self.reporter])
		conn = self.reporter.conn

		# We're creating a new in-memory database in make_reporter, so we don't need to worry about rows from previous tests.
		(build,) = list(conn.execute(Builds.select()))

		assert_equal(build['buildname'], 'a_build_name')
		assert_equal(build['branch'], 'a_branch_name')
		assert_equal(build['revision'], 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef')

		# Method count should be None until we discover (which is part of running)
		assert_equal(build['method_count'], None)
		# End time should be None until we run.
		assert_equal(build['end_time'], None)

		assert runner.run()

		# Now that we've run the tests, get the build row again and check to see that things are updated.
		(updated_build,) = list(conn.execute(Builds.select()))

		for key in updated_build.keys():
			if key not in ('end_time', 'run_time', 'method_count'):
				assert_equal(build[key], updated_build[key])

		assert_gt(updated_build['run_time'], 0)
		assert_in_range(updated_build['end_time'], 0, time.time())
		assert_equal(updated_build['method_count'], 2)

		# Check that we have one failure and one pass, and that they're the right tests.
		test_results = list(conn.execute(SA.select(
			columns=TestResults.columns + Tests.columns,
			from_obj=TestResults.join(Tests, TestResults.c.test == Tests.c.id)
		)))

		assert_equal(len(test_results), 2)
		(passed_test,) = [r for r in test_results if not r['failure']]
		(failed_test,) = [r for r in test_results if r['failure']]

		assert_equal(passed_test['method_name'], 'test_pass')
		assert_equal(failed_test['method_name'], 'test_fail')


	def test_update_counts(self):
		"""Tell our SQLReporter to update its counts, and check that it does."""
		conn = self.reporter.conn

		(build,) = list(conn.execute(Builds.select()))

		assert_equal(build['method_count'], None)

		self.reporter.test_counts(3, 50)
		(updated_build,) = list(conn.execute(Builds.select()))

		assert_equal(updated_build['method_count'], 50)

	def test_previous_run(self):
		"""Insert a test result with two previous runs, and make sure it works properly."""
		conn = self.reporter.conn

		test_case = DummyTestCase()
		results = [TestResult(test_case.test_pass) for _ in xrange(3)]

		previous_run = None
		for result in results:
			if previous_run:
				result.start(previous_run=previous_run.to_dict())
			else:
				result.start()

			result.end_in_success()
			previous_run = result

		self.reporter.test_complete(results[-1].to_dict())

		assert self.reporter.report() # Make sure all results are inserted.

		test_results = list(conn.execute(SA.select(
			columns=TestResults.columns + Tests.columns,
			from_obj=TestResults.join(Tests, TestResults.c.test == Tests.c.id)
		)))

		assert_equal(len(test_results), 3)

		for result in test_results:
			assert_equal(result['method_name'], 'test_pass')

