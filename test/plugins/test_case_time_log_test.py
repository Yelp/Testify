import contextlib
import datetime
import json
import mock
from optparse import OptionParser
import time

import six

from testify import compat
from testify import assert_equal, TestCase
from testify.test_result import TestResult
from testify.plugins.test_case_time_log import add_command_line_options, TestCaseJSONReporter


class MyStringIO(compat.NativeIO):
    def close(self):
        pass

    def _close():
        super(MyStringIO).close()


def _mock_conf_file_open(fname, mode='w'):
    return MyStringIO()


@contextlib.contextmanager
def mock_conf_files():
    with mock.patch.object(six.moves.builtins, 'open', _mock_conf_file_open):
        yield


start_time = datetime.datetime(2014, 12, 17, 12, 38, 37, 0)
end_time = datetime.datetime(2014, 12, 17, 15, 38, 37, 0)
output_str = (
    """{"normalized_run_time": "10800.00s", """
    """"complete": true, "start_time": %s, """
    """"runner_id": null, "failure": null, "run_time": %s, """
    """"previous_run": null, "success": null, "exception_info": null, """
    """"interrupted": null, """
    """"method": {"full_name": "testify.test_case TestCase.run", """
    """"fixture_type": null, "class": "TestCase", """
    """"module": "testify.test_case", "name": "run"}, """
    """"exception_info_pretty": null, "end_time": %s, "error": null, """
    """"exception_only": ""}\n""" % (time.mktime(start_time.timetuple()),
                                     str(time.mktime(end_time.timetuple()) - time.mktime(start_time.timetuple())),
                                     time.mktime(end_time.timetuple())))


class TestCaseJSONReporterTestCase(TestCase):

    def set_options(self):
        parser = OptionParser()
        add_command_line_options(parser)
        self.options, args = parser.parse_args([
            '--test-case-results', 'test_case_dummy.json'
        ])

    def test_json_reporter_reports(self):
        self.set_options()
        with mock_conf_files():
            self.reporter = TestCaseJSONReporter(self.options)
            test_case = TestCase()
            fake_test_result = TestResult(test_case.run)
            with mock.patch.object(
                datetime, 'datetime', **{'now.return_value': start_time}
            ):
                fake_test_result.start()
            with mock.patch.object(datetime, 'datetime', **{'now.return_value': end_time}):
                fake_test_result._complete()
            self.reporter.test_case_complete(fake_test_result.to_dict())
            assert_equal(
                json.loads(self.reporter.log_file.getvalue()),
                json.loads(output_str),
            )
