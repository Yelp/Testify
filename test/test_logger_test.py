import cStringIO

from test.discovery_failure_test import BrokenImportTestCase
from testify import TestCase, assert_equal, assert_in, run, setup, teardown
from testify.test_logger import ColorlessTextTestLogger, TextTestLogger, VERBOSITY_NORMAL
from testify.test_runner import TestRunner
from testify.utils import stringdiffer, turtle


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
        assert_in('DISCOVERY FAILURE!', logger_output)


class ColorlessTextTestLoggerTestCase(TestCase):

    class MockOptionsColor(object):
        disable_color = False

    class MockOptionsNoColor(object):
        disable_color = True

    def test_highlight_marker(self):
        ColorlessTextTestLogger(self.MockOptionsColor())
        colored_highlight_marker = stringdiffer.HighlightMarker()
        assert_equal(colored_highlight_marker.color, True)

        ColorlessTextTestLogger(self.MockOptionsNoColor())
        colorless_highlight_marker = stringdiffer.HighlightMarker()
        assert_equal(colorless_highlight_marker.color, False)


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
