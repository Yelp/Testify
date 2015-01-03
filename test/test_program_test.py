import os
import shutil
import subprocess
import tempfile
from os.path import join, exists

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

    def test_parse_test_runner_command_line_args_connect(self):
        """Make sure that when --connect is passed,
        parse_test_runner_command_line_args doesn't complain about a missing
        test path.
        """
        test_program.parse_test_runner_command_line_args([], ['--connect', 'localhost:65537'])

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
        output = test_call(['python', '-m', 'testify.test_program', '--help'])
        assert_in('Usage:', output)

    def test_run_testify_from_bin_list_tests(self):
        output = test_call(['bin/testify', '--list-tests', 'testing_suite'])
        assert_equal(output, self.expected_list)

    def test_run_testify_as_module_list_tests(self):
        output = test_call([
            'python', '-m', 'testify.test_program',
            '--list-tests', 'testing_suite'])
        assert_equal(output, self.expected_list)

    def test_run_testify_from_bin(self):
        output = test_call(['bin/testify', 'testing_suite', '-v'])
        assert_in(self.expected_tests, output)

    def test_run_testify_test_module(self):
        output = test_call(['python', '-m', 'testing_suite.example_test', '-v'])
        assert_in(self.expected_tests, output)

    def test_run_testify_test_file(self):
        output = test_call(['python', 'testing_suite/example_test.py', '-v'])
        assert_in(self.expected_tests, output)

    def test_run_testify_test_file_class(self):
        output = test_call([
            'python', 'testing_suite/example_test.py', '-v',
            'ExampleTestCase'])
        assert_in('PASSED.  2 tests', output)

    def test_run_testify_test_file_class_and_method(self):
        output = test_call([
            'python', 'testing_suite/example_test.py', '-v',
            'ExampleTestCase.test_one'])
        assert_in('PASSED.  1 test', output)

    def test_run_testify_with_failure(self):
        assert_raises(
            subprocess.CalledProcessError,
            test_call,
            ['python', 'testing_suite/example_test.py', 'DoesNotExist'])

    def test_failure_on_interrupt(self):
        with assert_raises(subprocess.CalledProcessError):
            test_call([
                'python', '-m', 'testify.test_program',
                'test.failing_test_interrupt'
            ])


class TestClientServerReturnCode(TestCase):
    def test_client_returns_zero_on_success(self):
        server_process = subprocess.Popen(
            [
                'python', '-m', 'testify.test_program',
                'testing_suite.example_test',
                '--serve', '9001',
            ],
            stdout=open(os.devnull, 'w'),
            stderr=open(os.devnull, 'w'),
        )
        # test_call has the side-effect of asserting the return code is 0
        ret = test_call([
            'python', '-m', 'testify.test_program',
            '--connect', 'localhost:9001',
        ])
        assert_in('PASSED', ret)
        assert_equal(server_process.wait(), 0)


class TestClientScheduling(TestCase):
    @setup_teardown
    def create_temporary_directory(self):
        self.tempdir = tempfile.mkdtemp()
        shutil.copy(
            join('test', 'failing_test_after_signal.py'), self.tempdir,
        )
        try:
            yield
        finally:
            shutil.rmtree(self.tempdir)

    def test_client_returns_nonzero_on_failure(self):
        tempdir = self.tempdir
        server_process = subprocess.Popen(
            [
                'python', '-m', 'testify.test_program',
                'failing_test_after_signal',
                '--serve', '9001',
                '--server-timeout', '10',
                '-v',
            ],
            stdout=open(os.devnull, 'w'),
            stderr=open(os.devnull, 'w'),
            cwd=tempdir,
        )

        # Read from both of the processes until we get some output
        # Then send sigint to that process
        # We're doing this as a synchronization mechanism to guarantee
        # two clients are connected to the server when the test fails.
        # The expected behaviour is that the failed test is not re-run on
        # the same client

        class Client(object):
            def __init__(self, number):
                filename = join(tempdir, str(number) + '.stdout')
                self.proc = subprocess.Popen(
                    [
                        'python', '-m', 'testify.test_program',
                        '--connect', 'localhost:9001',
                        '--runner-timeout', '5',
                        '-v',
                    ],
                    stdout=open(filename, 'w'),
                    stderr=open(os.devnull, 'w'),
                    env=dict(os.environ, client_num=str(number)),
                    cwd=tempdir,
                )
                self.number = number
                self.ready = False
                self.outfile = filename

        clients = [Client(1), Client(2)]
        while True:
            for client in clients:
                client.ready = exists(join(tempdir, str(client.number)))

            if all(client.ready for client in clients):
                # all ready!
                break

        # All of our tests are ready, send them 'go!' so they continue
        with open(join(tempdir, 'go!'), 'w'):
            pass

        assert_equal(clients[0].proc.wait(), 1)
        assert_equal(clients[1].proc.wait(), 1)
        assert_equal(server_process.wait(), 1)

        # The failing test should have been run on both clients
        for client in clients:
            client.output = open(client.outfile).read()
            assert_in('Intentional failure!', client.output)

        # The passing test should have been run on just one clients
        assert_equal(set([True, False]), set([
            'test_pass' in client.output
            for client in clients
        ]))

        for client in clients:
            if 'test_pass' in client.output:
                assert_in(
                    'FAILED.  2 tests / 2 cases: 1 passed, 1 failed.',
                    client.output
                )
            else:
                assert_in(
                    'FAILED.  1 test / 1 case: 0 passed, 1 failed.',
                    client.output,
                )


class Test240Regression(TestCase):
    def _test(self, testname):
        """Regression test for #240."""
        server_process = subprocess.Popen(
            [
                'python', '-m', 'testify.test_program',
                testname,
                '--serve', '9001',
                '-v',
            ],
            stdout=open(os.devnull, 'w'),
            stderr=open(os.devnull, 'w'),
        )
        client_1 = subprocess.Popen(
            [
                'python', '-m', 'testify.test_program',
                '--connect', 'localhost:9001',
                '-v',
            ],
            stdout=open(os.devnull, 'w'),
            stderr=open(os.devnull, 'w'),
        )
        assert_equal(client_1.wait(), 1)
        assert_equal(server_process.wait(), 1)

    def test_one_test_one_fail(self):
        self._test('test.failing_test')

    def test_lots_of_fails(self):
        """Not sure why three fails triggers this behaviour as well..."""
        self._test('test.lots_of_fail')
