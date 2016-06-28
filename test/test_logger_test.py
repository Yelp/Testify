from mock import patch

from testify import compat
from testify import exit
from testify import TestCase, assert_equal, assert_in, class_setup, class_setup_teardown, class_teardown, run, setup, teardown
from testify.test_logger import TextTestLogger, VERBOSITY_NORMAL
from testify.test_runner import TestRunner
from testify.utils import turtle


class TextLoggerBaseTestCase(TestCase):
    @setup
    def create_stream_for_logger(self):
        self.stream = compat.NativeIO()

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


class TextLoggerDiscoveryFailureTestCase(TextLoggerBaseTestCase):
    def test_text_test_logger_prints_discovery_failure_message(self):
        runner = TestRunner(
            'does.not.exist',
            test_reporters=[TextTestLogger(self.options, stream=self.stream)],
        )
        runner.run()
        logger_output = self.stream.getvalue()
        assert_in('DISCOVERY FAILURE!', logger_output)


class FakeClassFixtureException(Exception):
    pass


class ExceptionInClassFixtureSampleTests(TestCase):
    class FakeClassSetupTestCase(TestCase):
        @class_setup
        def class_setup_raises_exception(self):
            raise FakeClassFixtureException('class_setup kaboom')

        def test1(self):
            assert False, 'test1 should not be reached; class_setup should have aborted.'

        def test2(self):
            assert False, 'test2 should not be reached; class_setup should have aborted.'

    class FakeClassTeardownTestCase(TestCase):
        @class_teardown
        def class_teardown_raises_exception(self):
            raise FakeClassFixtureException('class_teardown kaboom')

        def test1(self):
            pass

        def test2(self):
            pass

    class FakeSetupPhaseOfClassSetupTeardownTestCase(TestCase):
        @class_setup_teardown
        def class_setup_teardown_raises_exception_in_setup_phase(self):
            raise FakeClassFixtureException('class_setup_teardown setup phase kaboom')
            yield  # Never reached
            # Empty teardown, also never reached

        def test1(self):
            pass

        def test2(self):
            pass

    class FakeTeardownPhaseOfClassSetupTeardownTestCase(TestCase):
        @class_setup_teardown
        def class_setup_teardown_raises_exception_in_teardown_phase(self):
            # Empty setup
            yield
            raise FakeClassFixtureException('class_setup_teardown teardown phase kaboom')

        def test1(self):
            pass

        def test2(self):
            pass


class TextLoggerExceptionInClassFixtureTestCase(TextLoggerBaseTestCase):
    """Tests how TextLogger handles exceptions in @class_[setup | teardown |
    setup_teardown]. Also an integration test with how results are collected
    because this seemed like the most natural place to test everything.
    """

    def _run_test_case(self, test_case):
        self.logger = TextTestLogger(self.options, stream=self.stream)
        runner = TestRunner(
            test_case,
            test_reporters=[self.logger],
        )
        runner_result = runner.run()
        assert_equal(runner_result, exit.TESTS_FAILED)

    def test_class_setup(self):
        self._run_test_case(ExceptionInClassFixtureSampleTests.FakeClassSetupTestCase)

        # The fake test methods assert if they are called. If we make it here,
        # then execution never reached those methods and we are happy.

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
        assert_in('error', logger_output)
        assert_in('FakeClassSetupTestCase.test1', logger_output)
        assert_in('FakeClassSetupTestCase.test2', logger_output)
        assert_in('in class_setup_raises_exception', logger_output)

    def test_setup_phase_of_class_setup_teardown(self):
        self._run_test_case(ExceptionInClassFixtureSampleTests.FakeSetupPhaseOfClassSetupTeardownTestCase)

        # The fake test methods assert if they are called. If we make it here,
        # then execution never reached those methods and we are happy.

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
        assert_in('error', logger_output)
        assert_in('FakeSetupPhaseOfClassSetupTeardownTestCase.test1', logger_output)
        assert_in('FakeSetupPhaseOfClassSetupTeardownTestCase.test2', logger_output)
        assert_in('in class_setup_teardown_raises_exception_in_setup_phase', logger_output)

    def test_class_teardown(self):
        self._run_test_case(ExceptionInClassFixtureSampleTests.FakeClassTeardownTestCase)
        assert_equal(len(self.logger.results), 3)

        class_teardown_result = self.logger.results[-1]
        assert_equal(
            class_teardown_result['success'],
            False,
            'Unexpected success for %s' % class_teardown_result['method']['full_name'],
        )
        assert_equal(
            class_teardown_result['error'],
            True,
            'Unexpected non-error for %s' % class_teardown_result['method']['full_name'],
        )

        logger_output = self.stream.getvalue()
        assert_in('error', logger_output)
        assert_in('FakeClassTeardownTestCase.class_teardown_raises_exception', logger_output)

    def test_teardown_phase_of_class_setup_teardown(self):
        self._run_test_case(ExceptionInClassFixtureSampleTests.FakeTeardownPhaseOfClassSetupTeardownTestCase)
        assert_equal(len(self.logger.results), 3)

        class_teardown_result = self.logger.results[-1]
        assert_equal(
            class_teardown_result['success'],
            False,
            'Unexpected success for %s' % class_teardown_result['method']['full_name'],
        )
        assert_equal(
            class_teardown_result['error'],
            True,
            'Unexpected non-error for %s' % class_teardown_result['method']['full_name'],
        )

        logger_output = self.stream.getvalue()
        assert_in('error', logger_output)
        assert_in(
            'FakeTeardownPhaseOfClassSetupTeardownTestCase.class_setup_teardown_raises_exception_in_teardown_phase',
            logger_output,
        )

    def test_class_teardown_raises_after_test_raises(self):
        """Patch our fake test case, replacing test1() with a function that
        raises its own exception. Make sure that both the method's exception
        and the class_teardown exception are represented in the results.
        """

        class FakeTestException(Exception):
            pass

        def test1_raises(self):
            raise FakeTestException('I raise before class_teardown raises')

        with patch.object(ExceptionInClassFixtureSampleTests.FakeClassTeardownTestCase, 'test1', test1_raises):
            self._run_test_case(ExceptionInClassFixtureSampleTests.FakeClassTeardownTestCase)

            assert_equal(len(self.logger.results), 3)
            test1_raises_result = self.logger.results[0]
            class_teardown_result = self.logger.results[-1]
            assert_in('FakeTestException', str(test1_raises_result['exception_info_pretty']))
            assert_in('FakeClassFixtureException', str(class_teardown_result['exception_info_pretty']))


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
