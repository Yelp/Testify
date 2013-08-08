import mock
from testify import assert_equal, assert_raises, setup_teardown, TestCase, test_program
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
        """Make sure _parse_test_runner_command_line_module_method_overrides returns something sensible if you pass it an empty list of arguments."""
        assert_equal(test_program._parse_test_runner_command_line_module_method_overrides([]), (None, {}))

    def test_parse_test_runner_command_line_args_rerun_test_file(self):
        """Make sure that when --rerun-test-file is passed, parse_test_runner_command_line_args doesn't complain about a missing test path."""
        test_program.parse_test_runner_command_line_args([], ['--rerun-test-file', '-'])

    def test_parse_test_runner_command_line_args_connect(self):
        """Make sure that when --connect is passed, parse_test_runner_command_line_args doesn't complain about a missing test path."""
        test_program.parse_test_runner_command_line_args([], ['--connect', 'localhost:65537'])

    def test_parse_test_runner_command_line_args_replay_json_inline(self):
        """Make sure that when --replay-json-inline is passed, parse_test_runner_command_line_args doesn't complain about a missing test path."""
        test_program.parse_test_runner_command_line_args([], ['--replay-json-inline', '{something that obviously isnt json}'])

    def test_parse_test_runner_command_line_args_replay_json(self):
        """Make sure that when --replay-json-inline is passed, parse_test_runner_command_line_args doesn't complain about a missing test path."""
        test_program.parse_test_runner_command_line_args([], ['--replay-json', 'somejsonfile.txt'])

    def test_parse_test_runner_command_line_args_no_test_path(self):
        """Make sure that if no options and no arguments are passed, parse_test_runner_command_line_args DOES complain about a missing test path."""
        with assert_raises(OptionParserErrorException):
            test_program.parse_test_runner_command_line_args([], [])
