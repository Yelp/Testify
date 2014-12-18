import __builtin__
import contextlib
import datetime
import mock
from optparse import OptionParser
from StringIO import StringIO
import time

from testify import assert_equal, assert_is, setup_teardown, TestCase
from testify.test_result import TestResult
from testify.test_runner import TestRunner
from testify.plugins.test_case_time_log import add_command_line_options, TestCaseJSONReporter

class DummyTestCase(TestCase):
    __test__ = False

    def test_pass(self):
        pass

    def test_fail(self):
        assert False

class MyStringIO(StringIO):
   def close(self):
       pass
   def _close():
       super(MyStringIO, self).close()

def _mock_conf_file_open(fname, mode='w'):
    return MyStringIO()

@contextlib.contextmanager
def mock_conf_files():
    #with mock.patch('service.db.initialize_db', mocked_initialize_db):
    with mock.patch('__builtin__.open', _mock_conf_file_open):
        yield

output_str = (
    """{"normalized_run_time": "10800.00s", """
   """"complete": true, "start_time": 1418848717.0, """
   """"runner_id": null, "failure": null, "run_time": 10800.0, """
   """"previous_run": null, "success": null, "exception_info": null, """
   """"interrupted": null, """
   """"method": {"full_name": "test.plugins.test_case_time_log_test DummyTestCase.test_pass", """
              """"fixture_type": null, "class": "DummyTestCase", """
              """"module": "test.plugins.test_case_time_log_test", "name": "test_pass"}, """
   """"exception_info_pretty": null, "end_time": 1418859517.0, "error": null, """
   """"exception_only": ""}\n""")

OUTPUT = MyStringIO(output_str)
start_time = datetime.datetime(2014, 12, 17, 12, 38, 37, 872046)
end_time = datetime.datetime(2014, 12, 17, 15, 38, 37, 872046)

class TestCaseJSONReporterTestCase(TestCase):

    def set_options(self):
        parser = OptionParser()
        add_command_line_options(parser)
        (self.options, args) = parser.parse_args([
            '--test-case-results', 'test_case_dummy.json'
        ])


    def test_http_reporter_reports(self):

        self.set_options()
        with mock_conf_files():
            self.reporter = TestCaseJSONReporter(self.options)
            test_case = DummyTestCase()
            fake_test_result = TestResult(test_case.test_pass)
            with mock.patch.object(
                datetime, 'datetime', **{'now.return_value': start_time}):
                fake_test_result.start()
            with mock.patch.object(datetime, 'datetime', **{'now.return_value': end_time}):
                fake_test_result._complete()
            self.reporter.test_case_complete(fake_test_result.to_dict())
            assert_equal(self.reporter.log_file.getvalue(), OUTPUT.getvalue())
