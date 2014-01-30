import mock

from testify import assert_equal
from testify import assert_raises
from testify import setup_teardown
from testify import run
from testify import TestCase
from testify.test_result import TestResult


def fake_format_exception(exctype, value, tb, limit=None):
    return 'Traceback: %s\n' % (exctype.__name__)


class TestResultTestCase(TestCase):

    @setup_teardown
    def mock_test_result(self):
        test_method = mock.Mock(__name__='test_name')
        with mock.patch('testify.TestCase.test_result', new_callable=mock.PropertyMock) as test_result:
            test_result.return_value = TestResult(test_method)
            yield

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
                (
                    'Traceback: Error1\n'
                    '\n'
                    'During handling of the above exception, another exception occurred:\n'
                    '\n'
                    'Traceback: Error2\n'
                )
        )


class TestResultStateTest(TestCase):
    """Make sure we don't have a test_result outside of a running test."""

    class WompTest(TestCase):

        @setup_teardown
        def assert_result_state(self):
            assert self.test_result
            yield
            assert self.test_result

        def test_success(self):
            pass

        def test_fail(self):
            assert False

    def test_results(self):
        test_suite = self.WompTest()

        # we only get a test_result once we enter setup
        assert test_suite.test_result is None

        with assert_raises(RuntimeError):
            # results? what results?!
            test_suite.results()

        test_suite.run()

        test_results = test_suite.results()

        assert_equal([result.success for result in test_results], [False, True])


if __name__ == "__main__":
    run()
