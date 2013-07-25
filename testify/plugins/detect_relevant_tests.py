"""Testify plugin for detecting tests relevant to a patchable target.

Use --help or see add_command_line_options for usage information.
"""
import functools
import sys

import mock

from testify.test_reporter import TestReporter


HUMAN_REPORT_FORMAT = '''
===== TESTS RELEVANT TO {relevant_to} DETECTED =====

NOTE: Use `--output-relevant-tests-to FILE` to write these to a file.
Then, you can run just those tests with `xargs testify < FILE`.

{relevant_tests}'''


def add_command_line_options(parser):
    """Adds command line options for the plugin to a given optparse parser."""
    parser.add_option(
        '--find-tests-relevant-to',
        dest='find_tests_relevant_to',
        default=None,
        metavar='TARGET',
        help=(
            'Record which tests make use of TARGET. TARGET should be a string '
            'referemce suitable for use with mock.patch.'
        ),
    )
    parser.add_option(
        '--output-relevant-tests-to',
        dest='output_relevant_tests_to',
        default=None,
        metavar='FILE',
        help=(
            'When used with --find-tests-relevant-to, writes the names of the '
            'relevant tests to FILE instead of printing them to stdout. This '
            'can be used to run just those tests via `xargs testify < FILE`.'
        )
    )


class RelevantTestReporter(TestReporter):
    """TestReporter for reporting tests relevant to a patchable target.

    RelevantTestReporter records whether a test is relevant by setting a
    relevance flag to False when the test_start hook is called, and checking
    the same flag once the test_complete hook is called. It relies on the
    declare_current_test_is_relevant method being called in-between if the test
    is detected to be relevant.
    """
    def __init__(self, options):
        # Store the parsed options for later reference.
        self.options = options

        # Accumulator for relevant tests.
        self.relevant_tests = []

        # Flag used to remember whether the current test is relevant.
        # TODO: Find a way to avoid using state like this, for perhaps by
        # adding a per-test Testify hook.
        self.__current_test_is_relevant = False

    def test_start(self, result):
        """To start, assume each test is not relevant to the target.

        Args:
            result - (ignored) a dict generated by TestResult.to_dict

        Modifies:
            self.__current_test_is_relevant
        """
        self.__current_test_is_relevant = False

    def declare_current_test_is_relevant(self):
        """Declares that the current test is relevant to the target.

        Modifies:
            self.__current_test_is_relevant
        """
        self.__current_test_is_relevant = True

    def test_complete(self, result):
        """Once each test is complete, record if we detected that it was
        relevant to the target.

        Args:
            result - a dict generated by TestResult.to_dict

        Modifies:
            self.relevant_tests
        """
        if self.__current_test_is_relevant:
            self.relevant_tests.append(result)

    def report(self):
        """Report the tests we detected were relevant to the target, either to
        stdout or a file depending on command line options."""
        # Make a newline-separated list of the names of the relevant tests.
        relevant_test_output = '\n'.join(
            (result.get('method') or {}).get('full_name')
            for result in self.relevant_tests
        )

        # If no file was specify, output the report formatted for humans.
        if self.options.output_relevant_tests_to is None:
            sys.stdout.write(HUMAN_REPORT_FORMAT.format(
                relevant_to=self.options.find_tests_relevant_to,
                relevant_tests=relevant_test_output
            ))
        # Otherwise, write the list of names to the given file.
        else:
            with open(self.options.output_relevant_tests_to, 'w') as output_file:
                output_file.write(relevant_test_output)


def wrap_with_hook(fn_to_wrap, hook_fn):
    """Wraps a callable to add a pre-call hook.

    Args:
        fn_to_wrap - callable to wrap
        hook_fn - callable, will be called before executing fn_to_wrap

    Returns:
        a wrapped version of fn_to_wrap that works identically except that
        it calls hook_fn before executing fn_to_wrap
    """
    @functools.wraps(fn_to_wrap)
    def wrapped(*a, **k):
        hook_fn()
        return fn_to_wrap(*a, **k)
    return wrapped


class RelevantTestReportingSystem(object):
    """System for coordinating the reporting of tests relevant to a target.

    This exists because the build_test_reporters and run_test_case Testify
    hooks need to share access to a single reporter object. Before executing
    a TestCase, run_test_case will patch the target so that it reports any
    calls of the target to the RelevantTestReporter that build_test_reporters
    creates. The RelevantTestReporter (self.reporter in this class) relies on
    this patching to accumulate a list of these tests.

    To see how this system is initialized as a Testify plugin, see `setup`.
    """
    # Will be overwritten with the RelevantTestReporter used to accumluate
    # relevant tests when the system is initialized via build_test_reporters.
    reporter = None

    def build_test_reporters(self, options):
        """Testify hook which sets up the reporter if the system is enabled.

        Args:
            options - optparse options

        Returns:
            [self.reporter] if enabled, else []

        Modifies:
            self.reporter, to contain a RelevantTestReporter
        """
        if options.find_tests_relevant_to is None:
            return []
        else:
            self.reporter = RelevantTestReporter(options)
            return [self.reporter]

    def run_test_case(self, options, test_case, runnable):
        """Testify hook which maybe patches the target and runs a TestCase.

        If the system is enabled, patches the target given in `options` so that
        it declares to self.reporter that the current test is relevant to the
        target if the target is called.

        Args:
            options - optparse options
            test_case - a testify TestCase
            runnable - callable which runs test_case

        Returns:
            the result of runnable
        """
        # If the system is disabled, just run the TestCase normally.
        if options.find_tests_relevant_to is None:
            return runnable()
        # If the system is enabled, patch the target so it reports its usage
        # to self.reporter, then run the TestCase.
        else:
            with mock.patch(
                options.find_tests_relevant_to,
                wrap_with_hook(
                    # TODO: Find a way to do this without using a _ function.
                    mock._importer(options.find_tests_relevant_to),
                    self.reporter.declare_current_test_is_relevant,
                )
            ):
                return runnable()

    @classmethod
    def setup(cls):
        """Helper for setting up the reporting system.

        To use this, call it and unpack the returns to `build_test_reporters`
        and `run_test_case` in the plugin module.

        Returns: (build_test_reporters, run_test_case)
            build_test_reporters - callable suitable to be used as the plugin's
                `build_test_reporters` hook
            run_test_case - callable suitable to be used as the plugin's
                `run_test_case` hoook
        """
        reporting_system = cls()
        return reporting_system.build_test_reporters, reporting_system.run_test_case


# Create a RelevantTestReportingSystem and set up the hooks it needs.
build_test_reporters, run_test_case = RelevantTestReportingSystem.setup()