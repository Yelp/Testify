import logging

from testify import assert_equal
from testify import assert_raises
from testify import class_setup
from testify import run
from testify import setup
from testify import TestCase
from testify.utils.mock_logging import MockHandler, mock_logging


class MockHandlerTest(TestCase):
    """Test and verify behaviour of MockHandler.
    """

    @class_setup
    def setup_logger(self):
        self.log = logging.getLogger('mocklogger_test')
        self.handler = MockHandler()
        self.log.handlers = [self.handler]

    @setup
    def clear_logger(self):
        self.handler.clear()

    def test_asserter(self):
        def helper_test_asserts():
            with self.handler.assert_logs():
                pass

        def helper_test_non_asserts():
            with self.log.assert_does_not_log():
                self.log.error("test error message 1")

        def helper_test_asserts_level():
            with self.log.assert_logs(levels=[logging.DEBUG]):
                self.log.log(logging.DEBUG, "test debug message 1")

        with assert_raises(AssertionError):
            with self.handler.assert_logs():
                pass
        with assert_raises(AssertionError):
            with self.handler.assert_does_not_log():
                self.log.error("test error message 2")
        with self.handler.assert_logs(levels=[logging.DEBUG]):
            self.log.debug("test debug message 2")
        with self.handler.assert_does_not_log(levels=[logging.DEBUG]):
            self.log.info("test debug message 3")


class MockLoggingTest(TestCase):
    """Test and verify behaviour of mock_logging context manager.
    """

    def test_mock_logging(self):
        with mock_logging() as mock_handler:
            logging.info("bananas")
            assert_equal(["bananas"], mock_handler.get(logging.INFO))

    def test_specific_mock_logging(self):
        with mock_logging(['mocklogger_test_2']) as mock_handler:
            logging.getLogger('mocklogger_test_2').info('banana1')
            logging.getLogger('mocklogger_test_3').info('banana2')
            assert_equal(["banana1"], mock_handler.get(logging.INFO))


if __name__ == '__main__':
    run()
