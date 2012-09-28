import cStringIO

from test.discovery_failure_test import BrokenImportTestCase
from testify import TestCase, assert_equal, assert_in, class_setup, class_teardown, run, setup, teardown
from testify.test_logger import TextTestLogger, VERBOSITY_NORMAL
from testify.test_runner import TestRunner
from testify.utils import turtle


class TextLoggerBaseTestCase(TestCase):
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


class TextLoggerDiscoveryFailureTestCase(BrokenImportTestCase, TextLoggerBaseTestCase):
    def test_text_test_logger_prints_discovery_failure_message(self):
        runner = TestRunner(
            self.broken_import_module,
            test_reporters=[TextTestLogger(self.options, stream=self.stream)],
        )
        runner.run()
        logger_output = self.stream.getvalue()
        assert_in('DISCOVERY FAILURE!', logger_output)


class TextLoggerExceptionInClassFixtureTestCase(TextLoggerBaseTestCase):
    """Tests how TextLogger handles exceptions in @class_[setup|teardown]. Also
    an integration test with how results are collected because this seemed like
    the most natural place to test everything.
    """

    class FakeClassFixtureException(Exception):
        pass

    class FakeClassSetupTestCase(TestCase):
        @class_setup
        def class_setup_raises_exception(self):
            raise TextLoggerExceptionInClassFixtureTestCase.FakeClassFixtureException

        def test1(self):
            print "i am test1"
            pass

        def test2(self):
            print "i am test2"
            pass

    class FakeClassTeardownTestCase(TestCase):
        @class_teardown
        def class_teardown_raises_exception(self):
            print "### BOOM teardown ###"
            raise TextLoggerExceptionInClassFixtureTestCase.FakeClassFixtureException

        def test1(self):
            print "i am test1"
            pass

        def test2(self):
            print "i am test2"
            pass

    def test_setup(self):
        ### Please also fill me out plz kthx.
        pass

    def test_teardown(self):
        logger = TextTestLogger(self.options, stream=self.stream)
        runner = TestRunner(
            TextLoggerExceptionInClassFixtureTestCase.FakeClassTeardownTestCase,
            test_reporters=[logger],
        )
        runner_result = runner.run()
        assert_equal(runner_result, False)

        for result in logger.results:
            assert_equal(
                result['success'],
                False,
                'Unexpected success for %s' % result['method']['full_name'],
            )
            assert_equal(
                result['error'],
                True,
                'Unexpected non-error for %s' % result['method']['full_name'],
            )

        logger_output = self.stream.getvalue()
        assert_in('class_teardown failed', logger_output)
        assert_in('from TestCase FakeClassTeardownTestCase as FAILED', logger_output)


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
