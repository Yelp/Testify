import mock

from testify import assert_equal
from testify import setup
from testify import run
from testify import TestCase
from testify.test_result import TestResult


class TestResultTestCase(TestCase):

    @setup
    def setup_test_result(self):
        self.test_method = mock.MagicMock(__name__='test_name')
        self.test_result = TestResult(self.test_method)

    def _set_exc_info(self, exc_type):
        value, tb = mock.Mock(), mock.Mock(tb_next=None)
        tb.tb_frame.f_globals.has_key.return_value = False
        self.test_result.exception_info = exc_type, value, tb
        return value, tb

    @mock.patch('testify.test_result.traceback.format_exception', autospec=True)
    def test_format_exception_info_assertion(self, mock_format_exception):
        value, tb = self._set_exc_info(AssertionError)
        formatted = self.test_result.format_exception_info()
        mock_format_exception.assert_called_with(AssertionError, value, tb, 1)
        assert_equal(formatted, mock_format_exception.return_value)

    @mock.patch('testify.test_result.traceback.format_exception', autospec=True)
    def test_format_exception_info_error(self, mock_format_exception):
        value, tb = self._set_exc_info(ValueError)
        formatted = self.test_result.format_exception_info()
        mock_format_exception.assert_called_with(ValueError, value, tb)
        assert_equal(formatted, mock_format_exception.return_value)

    @mock.patch('testify.test_result.fancy_tb_formatter')
    def test_format_exception_info_assertion_pretty(self, mock_format):
        value, tb = self._set_exc_info(AssertionError)
        formatted = self.test_result.format_exception_info(pretty=True)
        mock_format.assert_called_with(AssertionError, value, tb, 1)
        assert_equal(formatted, mock_format.return_value)

    @mock.patch('testify.test_result.fancy_tb_formatter')
    def test_format_exception_info_error_pretty(self, mock_format):
        value, tb = self._set_exc_info(ValueError)
        formatted = self.test_result.format_exception_info(pretty=True)
        mock_format.assert_called_with(ValueError, value, tb)
        assert_equal(formatted, mock_format.return_value)


if __name__ == "__main__":
    run()
