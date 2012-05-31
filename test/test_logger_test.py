import cStringIO

from test.discovery_failure_test import BrokenImportTestCase
from testify import assert_in, run, setup, teardown
from testify.test_logger import TextTestLogger, VERBOSITY_NORMAL
from testify.test_runner import TestRunner
from testify.utils import turtle


class TestTextLoggerDiscoveryFailureTestCase(BrokenImportTestCase):
    @setup
    def create_stream_for_logger(self):
        self.stream = cStringIO.StringIO()

    @setup
    def create_options_for_test_runner(self):
        """Fake an OptionParser-style options object."""
        self.options = turtle.Turtle(
            verbosity=VERBOSITY_NORMAL,
            summary_mode=False,
        )

    @teardown
    def close_stream_for_logger(self):
        self.stream.close()

    def test_text_test_logger_prints_discovery_failure_message(self):
        runner = TestRunner(
            self.broken_import_module,
            test_reporters=[TextTestLogger(self.options, stream=self.stream)],
        )
        runner.run()
        logger_output = self.stream.getvalue()
        assert_in("Discovery failure!", logger_output)


if __name__ == '__main__':
    run()
