from mock import patch
import sqlalchemy as SA
import time
from optparse import OptionParser

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json


from test.discovery_failure_test import BrokenImportTestCase
from testify import TestCase, assert_equal, assert_gt, assert_in,  assert_in_range, setup_teardown
from testify.plugins.sql_reporter import Builds, Failures, SQLReporter, TestResults, Tests, add_command_line_options
from testify.test_result import TestResult
from testify.test_runner import TestRunner

class DummyTestCase(TestCase):
    __test__ = False
    def test_pass(self):
        pass

    def test_fail(self):
        assert False

class SQLReporterBaseTestCase(TestCase):
    __test__ = False

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


class SQLReporterTestCase(SQLReporterBaseTestCase):
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

        # The discovery_failure column should exist and be False.
        assert 'discovery_failure' in build
        assert_equal(build['discovery_failure'], False)

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

    def test_traceback_size_limit(self):
        """Insert a failure with a long exception and make sure it gets truncated."""
        conn = self.reporter.conn

        test_case = DummyTestCase()
        result = TestResult(test_case.test_fail)
        result.start()
        result.end_in_failure((type(AssertionError), AssertionError('A' * 200), None))

        with patch.object(self.reporter.options, 'sql_traceback_size', 50):
            with patch.object(result, 'format_exception_info') as mock_format_exception_info:
                mock_format_exception_info.return_value = ["AssertionError: %s" % ('A' * 200), 'A' * 200]

                self.reporter.test_complete(result.to_dict())

            assert self.reporter.report()

        failure = conn.execute(Failures.select()).fetchone()
        assert_equal(len(failure.traceback), 50)
        assert_equal(len(failure.error), 50)
        assert_in('Exception truncated.', failure.traceback)
        assert_in('Exception truncated.', failure.error)


class SQLReporterDiscoveryFailureTestCase(SQLReporterBaseTestCase, BrokenImportTestCase):
    def test_sql_reporter_sets_discovery_failure_flag(self):
        runner = TestRunner(self.broken_import_module, test_reporters=[self.reporter])
        runner.run()

        conn = self.reporter.conn
        (build,) = list(conn.execute(Builds.select()))

        assert_equal(build['discovery_failure'], True)
        assert_equal(build['method_count'], 0)

# vim: set ts=4 sts=4 sw=4 et:
