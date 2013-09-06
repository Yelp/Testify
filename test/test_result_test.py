import mock

from testify import assert_equal
from testify import setup
from testify import run
from testify import TestCase
from testify.test_result import TestResult

def fake_format_exception(exctype, value, tb, limit=None):
    return 'Traceback: %s\n' % (exctype.__name__)

class TestResultTestCase(TestCase):

    @setup
    def setup_test_result(self):
        self.test_method = mock.MagicMock(__name__='test_name')
        self.test_result = TestResult(self.test_method)

    def _append_exc_info(self, exc_type):
        value, tb = mock.Mock(), mock.Mock(tb_next=None)
        tb.tb_frame.f_globals.has_key.return_value = False
        self.test_result.exception_infos.append((exc_type, value, tb))
        return value, tb

    @mock.patch('traceback.format_exception', wraps=fake_format_exception)
    def test_format_exception_info_assertion(self, mock_format_exception):
        value, tb = self._append_exc_info(AssertionError)
        formatted = self.test_result.format_exception_info()
        mock_format_exception.assert_called_with(AssertionError, value, tb, 1)
        assert_equal(formatted, 'Traceback: AssertionError\n')

    @mock.patch('traceback.format_exception', wraps=fake_format_exception)
    def test_format_exception_info_error(self, mock_format_exception):
        value, tb = self._append_exc_info(ValueError)
        formatted = self.test_result.format_exception_info()
        mock_format_exception.assert_called_with(ValueError, value, tb, None)
        assert_equal(formatted, 'Traceback: ValueError\n')

    @mock.patch('testify.test_result.fancy_tb_formatter')
    def test_format_exception_info_assertion_pretty(self, mock_format):
        value, tb = self._append_exc_info(AssertionError)
        formatted = self.test_result.format_exception_info(pretty=True)
        mock_format.assert_called_with(AssertionError, value, tb, 1)
        assert_equal(formatted, mock_format.return_value)

    @mock.patch('testify.test_result.fancy_tb_formatter')
    def test_format_exception_info_error_pretty(self, mock_format):
        value, tb = self._append_exc_info(ValueError)
        formatted = self.test_result.format_exception_info(pretty=True)
        mock_format.assert_called_with(ValueError, value, tb)
        assert_equal(formatted, mock_format.return_value)

    @mock.patch('traceback.format_exception', wraps=fake_format_exception)
    def test_format_exception_info_multiple(self, mock_format_exception):
        class Error1(Exception): pass
        class Error2(Exception): pass

        value1, tb1 = self._append_exc_info(Error1)
        value2, tb2 = self._append_exc_info(Error2)
        formatted = self.test_result.format_exception_info()
        mock_format_exception.assert_has_calls([
                mock.call(Error1, value1, tb1, None),
                mock.call(Error2, value2, tb2, None),
        ])
        assert_equal(
                formatted,
                ''.join((
                    'There were multiple errors in this test:\n',
                    'Traceback: Error1\n',
                    'Traceback: Error2\n',
                ))
        )



if __name__ == "__main__":
    run()
