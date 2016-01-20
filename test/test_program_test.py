import subprocess
import sys

import mock
from testify import setup_teardown, TestCase, test_program
from testify.assertions import assert_equal, assert_raises, assert_in
from optparse import OptionParser


class OptionParserErrorException(Exception):
    pass


class ParseTestRunnerCommandLineArgsTest(TestCase):
    @setup_teardown
    def patch_OptionParser_error(self):
        def new_error(*args, **kwargs):
            raise OptionParserErrorException(*args, **kwargs)
        with mock.patch.object(OptionParser, 'error', side_effect=new_error):
            yield

    def test__parse_test_runner_command_line_module_method_overrides_empty_input(self):
        """Make sure _parse_test_runner_command_line_module_method_overrides
        returns something sensible if you pass it an empty list of arguments.
        """
        assert_equal(test_program._parse_test_runner_command_line_module_method_overrides([]), (None, {}))

    def test_parse_test_runner_command_line_args_rerun_test_file(self):
        """Make sure that when --rerun-test-file is passed,
        parse_test_runner_command_line_args doesn't complain about a missing
        test path.
        """
        test_program.parse_test_runner_command_line_args([], ['--rerun-test-file', '-'])

    def test_parse_test_runner_command_line_args_replay_json_inline(self):
        """Make sure that when --replay-json-inline is passed,
        parse_test_runner_command_line_args doesn't complain about a missing
        test path.
        """
        test_program.parse_test_runner_command_line_args([], ['--replay-json-inline', '{something that obviously isnt json}'])

    def test_parse_test_runner_command_line_args_replay_json(self):
        """Make sure that when --replay-json-inline is passed,
        parse_test_runner_command_line_args doesn't complain about a missing
        test path.
        """
        test_program.parse_test_runner_command_line_args([], ['--replay-json', 'somejsonfile.txt'])

    def test_parse_test_runner_command_line_args_no_test_path(self):
        """Make sure that if no options and no arguments are passed,
        parse_test_runner_command_line_args DOES complain about a missing test
        path.
        """
        with assert_raises(OptionParserErrorException):
            test_program.parse_test_runner_command_line_args([], [])


def test_call(command):
    proc = subprocess.Popen(command, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, command)
    return stdout.strip().decode('UTF-8')


class TestifyRunAcceptanceTestCase(TestCase):

    expected_list = (
        'testing_suite.example_test ExampleTestCase.test_one\n'
        'testing_suite.example_test ExampleTestCase.test_two\n'
        'testing_suite.example_test SecondTestCase.test_one'
    )

    expected_tests = 'PASSED.  3 tests'

    def test_help(self):
        output = test_call([sys.executable, '-m', 'testify.test_program', '--help'])
        assert_in('Usage:', output)

    def test_run_testify_from_bin_list_tests(self):
        output = test_call(['bin/testify', '--list-tests', 'testing_suite'])
        assert_equal(output, self.expected_list)

    def test_run_testify_as_module_list_tests(self):
        output = test_call([
            sys.executable, '-m', 'testify.test_program',
            '--list-tests', 'testing_suite'])
        assert_equal(output, self.expected_list)

    def test_run_testify_from_bin(self):
        output = test_call(['bin/testify', 'testing_suite', '-v'])
        assert_in(self.expected_tests, output)

    def test_run_testify_test_module(self):
        output = test_call([sys.executable, '-m', 'testing_suite.example_test', '-v'])
        assert_in(self.expected_tests, output)

    def test_run_testify_test_file(self):
        output = test_call([sys.executable, 'testing_suite/example_test.py', '-v'])
        assert_in(self.expected_tests, output)

    def test_run_testify_test_file_class(self):
        output = test_call([
            sys.executable, 'testing_suite/example_test.py', '-v',
            'ExampleTestCase'])
        assert_in('PASSED.  2 tests', output)

    def test_run_testify_test_file_class_and_method(self):
        output = test_call([
            sys.executable, 'testing_suite/example_test.py', '-v',
            'ExampleTestCase.test_one'])
        assert_in('PASSED.  1 test', output)

    def test_run_testify_with_failure(self):
        assert_raises(
            subprocess.CalledProcessError,
            test_call,
            [sys.executable, 'testing_suite/example_test.py', 'DoesNotExist'])

    def test_failure_on_interrupt(self):
        with assert_raises(subprocess.CalledProcessError):
            test_call([
                sys.executable, '-m', 'testify.test_program',
                'test.failing_test_interrupt'
            ])

    def test_rerun_with_failure_limit(self):
        proc = subprocess.Popen(
            (
                sys.executable, '-m', 'testify.test_program',
                '--rerun-test-file=/dev/stdin',
                '--failure-limit', '1',
            ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout, _ = proc.communicate(
            b'test.fails_two_tests FailsTwoTests.test1\n'
            b'test.fails_two_tests FailsTwoTests.test2\n'
        )
        assert_in(b'FAILED.  1 test / 1 case: 0 passed, 1 failed.', stdout)
