import __builtin__
import StringIO
try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json

from testify import assert_equal
from testify import run
from testify import setup
from testify import teardown
from testify import test_case
from testify import test_result
from testify.plugins import json_log
from testify.utils import turtle


class JSONReporterTestCase(test_case.TestCase):

    class BaseTestCase(test_case.TestCase):
        def test_method(self):
            return

    BaseTestCase.__module__ = 'base'

    class ExtendedTestCase(BaseTestCase):
        pass

    ExtendedTestCase.__module__ = 'extended'

    extended_test_case = ExtendedTestCase()

    json_reporter_options = turtle.Turtle(json_results_logging=True,
                                          json_results=None,
                                          label=None,
                                          extra_json_info=None,
                                          bucket=None,
                                          bucket_count=None,
                                          verbosity=0)

    @setup
    def setup(self):
        """Monkey patch `open` to point to a `StringIO()` at `self.log_file`
        and create a new `JSONReporter`.
        """
        self._open = __builtin__.open
        self.log_file = StringIO.StringIO()
        # Prevent the mock log file from being closed.
        self._log_file_close = self.log_file.close
        self.log_file.close = lambda: None
        __builtin__.open = lambda *args: self.log_file

        self.json_reporter = json_log.JSONReporter(self.json_reporter_options)

    @teardown
    def teardown(self):
        """Restore `open` and close `self.log_file`."""
        __builtin__.open = self._open

        self.log_file.close = self._log_file_close
        self.log_file.close()

    def test_report_extended_test_module_name(self):
        """When `JSONReporter` logs the results for a test, make sure it
        records the module that the test method's `TestCase` is in, and not the
        module of the `TestCase`'s base class that defined the method.

        Regression test for GitHub #13.
        """

        result = test_result.TestResult(self.extended_test_case.test_method)

        self.json_reporter.test_start(result.to_dict())

        result.start()
        result.end_in_success()

        self.json_reporter.test_complete(result.to_dict())
        assert_equal(True, self.json_reporter.report())

        log_lines = ''.join(line for line in
                            self.log_file.getvalue().splitlines()
                            if line != 'RUN COMPLETE')

        result = json.loads(log_lines)

        assert_equal('extended', result['method']['module'])
        assert_equal('extended ExtendedTestCase.test_method', result['method']['full_name'])


if __name__ == '__main__':
    run()
