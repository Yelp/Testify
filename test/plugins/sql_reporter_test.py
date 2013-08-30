from mock import patch
import time
from optparse import OptionParser

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json

SA = None
try:
    import sqlalchemy as SA
except ImportError:
    pass

from test.discovery_failure_test import BrokenImportTestCase
from test.test_logger_test import ExceptionInClassFixtureSampleTests
from test.test_case_test import RegexMatcher
from testify import TestCase, assert_equal, assert_gt, assert_in,  assert_in_range, setup_teardown
from testify.plugins.sql_reporter import add_command_line_options, SQLReporter
from testify.test_result import TestResult
from testify.test_runner import TestRunner

class DummyTestCase(TestCase):
    __test__ = False
    def test_pass(self):
        pass

    def test_fail(self):
        assert False

    def test_multiline(self):
        raise Exception("""I love lines:
    1
        2
            3""")

class SQLReporterBaseTestCase(TestCase):
    __test__ = False

    @setup_teardown
    def make_reporter(self):
        """Make self.reporter, a SQLReporter that runs on an empty in-memory SQLite database."""
        if not SA:
            msg = 'SQL Reporter plugin requires sqlalchemy and you do not have it installed in your PYTHONPATH.\n'
            raise ImportError, msg

        parser = OptionParser()
        add_command_line_options(parser)
        self.fake_buildbot_run_id = 'A' * 36
        (options, args) = parser.parse_args([
            '--reporting-db-url', 'sqlite://',
            '--sql-reporting-frequency', '0.05',
            '--build-info', json.dumps({
                'buildbot' : 1,
                'buildnumber' : 1,
                'buildbot_run_id': self.fake_buildbot_run_id,
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

    def _get_test_results(self, conn):
        """Return a list of tests and their results from SA connection `conn`."""
        return list(conn.execute(SA.select(
            columns=(
                self.reporter.TestResults,
                self.reporter.Tests,
                self.reporter.Failures,
            ),
            from_obj=self.reporter.TestResults.join(
                self.reporter.Tests,
                self.reporter.TestResults.c.test == self.reporter.Tests.c.id
            ).outerjoin(
                self.reporter.Failures,
                self.reporter.TestResults.c.failure == self.reporter.Failures.c.id
            )
        )))


class SQLReporterTestCase(SQLReporterBaseTestCase):
    def test_integration(self):
        """Run a runner with self.reporter as a test reporter, and verify a bunch of stuff."""
        runner = TestRunner(DummyTestCase, test_reporters=[self.reporter])
        conn = self.reporter.conn

        # We're creating a new in-memory database in make_reporter, so we don't need to worry about rows from previous tests.
        (build,) = list(conn.execute(self.reporter.Builds.select()))

        assert_equal(build['buildname'], 'a_build_name')
        assert_equal(build['branch'], 'a_branch_name')
        assert_equal(build['revision'], 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef')
        assert_equal(build['buildbot_run_id'], self.fake_buildbot_run_id)

        # Method count should be None until we discover (which is part of running)
        assert_equal(build['method_count'], None)
        # End time should be None until we run.
        assert_equal(build['end_time'], None)

        assert runner.run()

        # Now that we've run the tests, get the build row again and check to see that things are updated.
        (updated_build,) = list(conn.execute(self.reporter.Builds.select()))

        for key in updated_build.keys():
            if key not in ('end_time', 'run_time', 'method_count'):
                assert_equal(build[key], updated_build[key])

        assert_gt(updated_build['run_time'], 0)
        assert_in_range(updated_build['end_time'], 0, time.time())
        assert_equal(updated_build['method_count'], 3)

        # The discovery_failure column should exist and be False.
        assert 'discovery_failure' in build
        assert_equal(build['discovery_failure'], False)

        # Check test results.
        test_results = self._get_test_results(conn)
        assert_equal(len(test_results), 3)

        # Check that we have one failure and one pass, and that they're the right tests.
        (passed_test,) = [r for r in test_results if not r['failure']]
        (failed_test, failed_test_2) = [r for r in test_results if r['failure']]

        assert_equal(passed_test['method_name'], 'test_pass')
        assert_equal(passed_test.traceback, None)
        assert_equal(passed_test.error, None)

        assert_equal(failed_test['method_name'], 'test_fail')
        assert_equal(failed_test.traceback.split('\n'), [
            'Traceback (most recent call last):',
            RegexMatcher('  File "\./test/plugins/sql_reporter_test\.py", line \d+, in test_fail'),
            '    assert False',
            'AssertionError',
            '' # ends with newline
        ])
        assert_equal(failed_test.error, 'AssertionError')

        assert_equal(failed_test_2['method_name'], 'test_multiline')
        assert_equal(failed_test_2.traceback.split('\n'), [
            'Traceback (most recent call last):',
            RegexMatcher('  File "\./test/plugins/sql_reporter_test\.py", line \d+, in test_multiline'),
            '    3""")',
            'Exception: I love lines:',
            '    1',
            '        2',
            '            3',
            '' # ends with newline
        ])
        assert_equal(failed_test_2.error, 'Exception: I love lines:\n    1\n        2\n            3')



    def test_update_counts(self):
        """Tell our SQLReporter to update its counts, and check that it does."""
        conn = self.reporter.conn

        (build,) = list(conn.execute(self.reporter.Builds.select()))

        assert_equal(build['method_count'], None)

        self.reporter.test_counts(3, 50)
        (updated_build,) = list(conn.execute(self.reporter.Builds.select()))

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

        test_results = self._get_test_results(conn)
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
                mock_format_exception_info.return_value = "AssertionError: %s\n%s\n" % ('A' * 200, 'A' * 200)

                self.reporter.test_complete(result.to_dict())

            assert self.reporter.report()

        failure = conn.execute(self.reporter.Failures.select()).fetchone()
        assert_equal(len(failure.traceback), 50)
        assert_equal(len(failure.error), 50)
        assert_in('Exception truncated.', failure.traceback)
        assert_in('Exception truncated.', failure.error)


class SQLReporterDiscoveryFailureTestCase(SQLReporterBaseTestCase, BrokenImportTestCase):
    def test_sql_reporter_sets_discovery_failure_flag(self):
        runner = TestRunner(self.broken_import_module, test_reporters=[self.reporter])
        runner.run()

        conn = self.reporter.conn
        (build,) = list(conn.execute(self.reporter.Builds.select()))

        assert_equal(build['discovery_failure'], True)
        assert_equal(build['method_count'], 0)


class SQLReporterExceptionInClassFixtureTestCase(SQLReporterBaseTestCase):
    def test_setup(self):
        runner = TestRunner(ExceptionInClassFixtureSampleTests.FakeClassSetupTestCase, test_reporters=[self.reporter])
        runner.run()

        conn = self.reporter.conn

        test_results = self._get_test_results(conn)
        assert_equal(len(test_results), 2)

        # Errors in class_setup methods manifest as errors in the test case's
        # test methods.
        for result in test_results:
            assert_equal(
                result['failure'],
                True,
                'Unexpected success for %s.%s' % (result['class_name'], result['method_name'])
            )

        failures = conn.execute(self.reporter.Failures.select()).fetchall()
        for failure in failures:
            assert_in('in class_setup_raises_exception', failure.traceback)


    def test_teardown(self):
        runner = TestRunner(ExceptionInClassFixtureSampleTests.FakeClassTeardownTestCase, test_reporters=[self.reporter])
        runner.run()

        conn = self.reporter.conn

        test_results = self._get_test_results(conn)
        assert_equal(len(test_results), 3)

        # Errors in class_teardown methods manifest as an additional test
        # result.
        class_teardown_result = test_results[-1]
        assert_equal(
            class_teardown_result['failure'],
            True,
            'Unexpected success for %s.%s' % (class_teardown_result['class_name'], class_teardown_result['method_name'])
        )

        failure = conn.execute(self.reporter.Failures.select()).fetchone()
        assert_in('in class_teardown_raises_exception', failure.traceback)


class SQLReporterTestCompleteIgnoresResultsForRun(SQLReporterBaseTestCase):
    def test_test_complete(self):
        assert_equal(self.reporter.result_queue.qsize(), 0)

        test_case = DummyTestCase()
        fake_test_result = TestResult(test_case.run)
        self.reporter.test_complete(fake_test_result.to_dict())

        assert_equal(self.reporter.result_queue.qsize(), 0)


class SQLReporterReportResultsByChunk(SQLReporterBaseTestCase):
    def test_happy_path(self):
        conn = self.reporter.conn
        test_case = DummyTestCase()
        results = [
            TestResult(test_case.test_pass),
            TestResult(test_case.test_fail),
        ]
        chunk = []
        for result in results:
            result.start()
            result.end_in_success()
            chunk.append(result.to_dict())

        # In production, Someone Else takes care of manipulating the reporter's
        # result_queue. We'll just mock the method we care about to avoid
        # violating the Law of Demeter.
        with patch.object(self.reporter.result_queue, 'task_done') as mock_task_done:
            self.reporter._report_results_by_chunk(conn, chunk)
            assert_equal(len(results), mock_task_done.call_count)

        test_results = self._get_test_results(conn)
        assert_equal(len(results), len(test_results))


# vim: set ts=4 sts=4 sw=4 et:
