# Copyright 2009 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""This module contains classes and constants related to outputting test results."""

import collections
import logging
import os
import subprocess
import sys

import six

from testify import test_reporter


__testify = 1

VERBOSITY_SILENT = 0  # Don't say anything, just exit with a status code
VERBOSITY_NORMAL = 1  # Output dots for each test method run
VERBOSITY_VERBOSE = 2  # Output method names and timing information


class TestLoggerBase(test_reporter.TestReporter):

    def __init__(self, options, stream=sys.stdout):
        super(TestLoggerBase, self).__init__(options)
        self.stream = stream
        self.results = []
        self.test_case_classes = set()

    def test_start(self, result):
        self.test_case_classes.add((result['method']['module'], result['method']['class']))
        self.report_test_name(result['method'])

    def test_complete(self, result):
        self.report_test_result(result)
        self.results.append(result)
        if not result['success']:
            self.report_failure(result)

    def fixture_start(self, result):
        self.test_case_classes.add((result['method']['module'], result['method']['class']))

    def class_teardown_complete(self, result):
        if not result['success']:
            self.report_test_name(result['method'])
            self.report_test_result(result)
            self.results.append(result)

    def report(self):
        # All the TestCases have been run - now collate results by status and log them
        results_by_status = collections.defaultdict(list)
        for result in self.results:
            if result['success']:
                results_by_status['successful'].append(result)
            elif result['failure'] or result['error']:
                results_by_status['failed'].append(result)
            elif result['interrupted']:
                results_by_status['interrupted'].append(result)
            else:
                results_by_status['unknown'].append(result)

        if self.options.summary_mode:
            self.report_failures(results_by_status['failed'])
        self.report_stats(len(self.test_case_classes), **results_by_status)

        if len(self.results) == 0:
            return False
        else:
            return (
                (
                    len(results_by_status['failed']) +
                    len(results_by_status['interrupted']) +
                    len(results_by_status['unknown'])
                ) == 0
            )

    def report_test_name(self, test_method):
        pass

    def report_test_result(self, result):
        pass

    def report_failures(self, failed_results):
        if failed_results:
            self.heading('FAILURES', 'The following tests are expected to pass.')
            for result in failed_results:
                self.failure(result)
        else:
            # throwing this in so that someone looking at the bottom of the
            # output won't have to scroll up to figure out whether failures
            # were expected or not.
            self.heading('FAILURES', 'None!')

    def report_failure(self, result):
        pass

    def report_stats(self, test_case_count, all_results, failed_results, unknown_results):
        pass

    def _format_test_method_name(self, test_method):
        """Take a test method as input and return a string for output"""
        if test_method['module'] != '__main__':
            return "%s %s.%s" % (test_method['module'], test_method['class'], test_method['name'])
        else:
            return "%s.%s" % (test_method['class'], test_method['name'])


class TextTestLogger(TestLoggerBase):
    def __init__(self, options, stream=sys.stdout):
        super(TextTestLogger, self).__init__(options, stream)

        # Checking for color support isn't as fun as we might hope.  We're
        # going to use the command 'tput colors' to get a list of colors
        # supported by the shell. But of course we if this fails terribly,
        # we'll want to just fall back to no colors
        self.use_color = False
        # if TERM is not present in environ, tput prints to stderr
        # if tput's stderr is a pipe, it lies.
        if sys.stdin.isatty() and 'TERM' in os.environ:
            try:
                output = subprocess.check_output(('tput', 'colors'))
                if int(output.strip()) >= 8:
                    self.use_color = True
            except Exception as e:
                if self.options.verbosity >= VERBOSITY_VERBOSE:
                    self.writeln("Failed to find color support: %r" % e)

    def write(self, message):
        """Write a message to the output stream, no trailing newline"""
        if six.PY2:
            self.stream.write(message.encode('UTF-8') if isinstance(message, six.text_type) else message)
        else:
            self.stream.write(message.decode('UTF-8') if isinstance(message, bytes) else message)
        self.stream.flush()

    def writeln(self, message):
        """Write a message and append a newline"""
        self.write(message)
        self.write('\n')

    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(30, 38)

    def _colorize(self, message, color=CYAN):
        if not color or not self.use_color:
            return message
        else:
            start_color = '\033[1;%sm' % color
            end_color = '\033[m'
            return start_color + message + end_color

    def test_discovery_failure(self, exc):
        self.writeln(self._colorize("DISCOVERY FAILURE!", self.MAGENTA))
        self.writeln("There was a problem importing one or more tests:")
        self.writeln(str(exc))

    def report_test_name(self, test_method):
        if self.options.verbosity >= VERBOSITY_VERBOSE:
            self.write("%s ... " % self._format_test_method_name(test_method))

    def report_test_result(self, result):
        if self.options.verbosity > VERBOSITY_SILENT:
            if result['success']:
                if result['previous_run']:
                    status = "flaky"
                else:
                    status = "success"
            elif result['failure']:
                status = "fail"
            elif result['error']:
                status = "error"
            elif result['interrupted']:
                status = "interrupted"
            else:
                status = "unknown"

            status_description, status_letter, color = {
                "success": ('ok', '.', self.GREEN),
                "flaky": ('flaky', '!', self.YELLOW),
                "fail": ('FAIL', 'F', self.RED),
                "error": ('ERROR', 'E', self.RED),
                "interrupted": ('INTERRUPTED', '-', self.YELLOW),
                "unknown": ('UNKNOWN', '?', None),
            }[status]

            if status in ('fail', 'error'):
                self.writeln("\n%s: %s\n%s" % (status, self._format_test_method_name(result['method']), result['exception_info']))

            if self.options.verbosity == VERBOSITY_NORMAL:
                self.write(self._colorize(status_letter, color))
            elif result['normalized_run_time']:
                self.writeln("%s in %s" % (self._colorize(status_description, color), result['normalized_run_time']))
            else:
                self.writeln(self._colorize(status_description, color))

    def heading(self, *messages):
        self.writeln("")
        self.writeln("=" * 72)
        for line in messages:
            self.writeln(line)

    def failure(self, result):
        self.writeln("")
        self.writeln("=" * 72)
        self.writeln(self._format_test_method_name(result['method']))

        if self.use_color:
            self.writeln(result['exception_info_pretty'])
        else:
            self.writeln(result['exception_info'])

        self.writeln('=' * 72)
        self.writeln("")

    def report_stats(self, test_case_count, **results):
        successful = results.get('successful', [])
        failed = results.get('failed', [])
        interrupted = results.get('interrupted', [])
        unknown = results.get('unknown', [])

        test_method_count = sum(len(bucket) for bucket in results.values())
        test_word = "test" if test_method_count == 1 else "tests"
        case_word = "case" if test_case_count == 1 else "cases"
        overall_success = not failed and not unknown and not interrupted

        self.writeln('')

        if overall_success:
            if successful:
                status_string = self._colorize("PASSED", self.GREEN)
            else:
                if test_method_count == 0:
                    self.writeln(
                        "No tests were discovered (tests must subclass TestCase and test methods must begin with 'test').",
                    )
                status_string = self._colorize("ERROR", self.MAGENTA)
        else:
            status_string = self._colorize("FAILED", self.RED)

        self.write("%s.  " % status_string)
        self.write("%d %s / %d %s: " % (test_method_count, test_word, test_case_count, case_word))

        passed_string = self._colorize("%d passed" % len(successful), (self.GREEN if len(successful) else None))

        failed_string = self._colorize("%d failed" % len(failed), (self.RED if len(failed) else None))

        self.write("%s, %s.  " % (passed_string, failed_string))

        total_test_time = sum(
            (result['run_time'] for result in (successful + failed + interrupted)),
        )
        self.writeln("(Total test time %.2fs)" % total_test_time)


class ColorlessTextTestLogger(TextTestLogger):
    def _colorize(self, message, color=None):
        return message


class TestResultGrabberHandler(logging.Handler):
    """Logging handler to store log message during a test run"""

    def emit(self, record):
        raise Exception(repr(record))

# vim: set ts=4 sts=4 sw=4 et:
