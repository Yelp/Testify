import cStringIO

from mock import patch

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
            raise TextLoggerExceptionInClassFixtureTestCase.FakeClassFixtureException("class_setup kaboom")

        def test1(self):
            print "i am test1"
            pass

        def test2(self):
            print "i am test2"
            pass

    class FakeClassTeardownTestCase(TestCase):
        @class_teardown
        def class_teardown_raises_exception(self):
            raise TextLoggerExceptionInClassFixtureTestCase.FakeClassFixtureException("class_teardown kaboom")

        def test1(self):
            pass

        def test2(self):
            pass

    def _run_tests(self):
        self.logger = TextTestLogger(self.options, stream=self.stream)
        runner = TestRunner(
            TextLoggerExceptionInClassFixtureTestCase.FakeClassTeardownTestCase,
            test_reporters=[self.logger],
        )
        runner_result = runner.run()
        assert_equal(runner_result, False)


    def test_setup(self):
        ### Please also fill me out plz kthx.
        pass

    def test_teardown(self):
        self._run_tests()

        for result in self.logger.results:
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


    def test_teardown_raises_after_test_raises(self):
        """Patch our fake test case, replacing test1() with a function that
        raises its own exception. Make sure that both the method's exception
        and the class_teardown exception are represented in the results.
        """

        class FakeTestException(Exception):
            pass

        def test1_raises(self):
            raise FakeTestException("I raise before class_teardown raises")

        with patch.object(TextLoggerExceptionInClassFixtureTestCase.FakeClassTeardownTestCase, 'test1', test1_raises):
            self._run_tests()

            test1_raises_result = self.logger.results[0]
            test2_result = self.logger.results[1]
            assert_equal(
                len(test1_raises_result['exception_info']),
                2 * len(test2_result['exception_info']),
            )
            assert_in('FakeClassFixtureException', test1_raises_result['exception_info_pretty'])
            assert_in('FakeTestException', test1_raises_result['exception_info_pretty'])


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
