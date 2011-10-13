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
__testify = 1

import collections
import datetime
import logging
import operator
import subprocess
import sys
import traceback

# If IPython is available, use it for fancy color traceback formatting
try:
    try:
        # IPython >= 0.11
        from IPython.core.ultratb import ColorTB
        _hush_pyflakes = [ColorTB]
        del _hush_pyflakes
    except ImportError:
        # IPython < 0.11
        from IPython.ultraTB import ColorTB

    fancy_tb_formatter = staticmethod(ColorTB().text)
except ImportError:
    fancy_tb_formatter = staticmethod(traceback.format_exception)

from testify import test_reporter
from testify.test_case import TestCase

# Beyond the nicely formatted test output provided by the test logger classes, we
# also want to make basic test running /result info available via standard python logger
_log = logging.getLogger('testify')

VERBOSITY_SILENT    = 0  # Don't say anything, just exit with a status code
VERBOSITY_NORMAL    = 1  # Output dots for each test method run
VERBOSITY_VERBOSE   = 2  # Output method names and timing information

class TestLoggerBase(test_reporter.TestReporter):
    traceback_formatter = staticmethod(traceback.format_exception)

    def __init__(self, options, stream=sys.stdout):
        super(TestLoggerBase, self).__init__(options)
        self.stream = stream
        self.results = []
        self.test_case_classes = set()

    def test_start(self, test_case, test_method):
        self.test_case_classes.add(test_case.__class__)
        if not test_case.is_fixture_method(test_method) and not test_case.method_excluded(test_method):
            self.report_test_name(test_method)

    def test_complete(self, test_case, result):
        if not test_case.is_fixture_method(result.test_method):
            if not test_case.method_excluded(result.test_method):
                self.report_test_result(result)
            self.results.append(result)
        elif result.test_method._fixture_type == 'class_teardown' and (result.failure or result.error):
            # For a class_teardown failure, log the name too (since it wouldn't have
            # already been logged by on_run_test_method).
            self.report_test_name(result.test_method)
            self.report_test_result(result)

            self.results.append(result)

        if not result.success and not TestCase.in_suite(result.test_method, 'expected-failure'):
            self.report_failure(result)

    def report(self):
        # All the TestCases have been run - now collate results by status and log them
        results_by_status = collections.defaultdict(list)
        for result in self.results:
            if result.success:
                if result.unexpected_success:
                    results_by_status['unexpected_success'].append(result)
                else:
                    results_by_status['successful'].append(result)
            elif result.failure or result.error:
                results_by_status['failed'].append(result)
            elif result.incomplete:
                results_by_status['incomplete'].append(result)
            else:
                results_by_status['unknown'].append(result)

        if self.options.summary_mode:
            self.report_failures(results_by_status['failed'])
        self.report_stats(len(self.test_case_classes), **results_by_status)

        return bool((len(results_by_status['failed']) + len(results_by_status['unknown'])) == 0)

    def report_test_name(self, test_name):
        pass
    def report_test_result(self, result):
        pass

    def report_failures(self, failed_results):
        results = {
            'FAILURES': [],
            'EXPECTED_FAILURES': []
            }

        [results['EXPECTED_FAILURES'].append(result) if result.expected_failure else results['FAILURES'].append(result) for result in failed_results]

        if results['EXPECTED_FAILURES']:
            self.heading('EXPECTED FAILURES', 'The following tests have been marked expected-failure.')
            for result in results['EXPECTED_FAILURES']:
                self.failure(result)

        if results['FAILURES']:
            self.heading('FAILURES', 'The following tests are expected to pass.')
            for result in results['FAILURES']:
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
        out = []
        if test_method.im_class.__module__ != "__main__":
            out.append("%s " % test_method.im_class.__module__)
        out.append("%s.%s" % (test_method.im_class.__name__, test_method.__name__))

        return ''.join(out)

    # Helper methods for extracting relevant entries from a stack trace
    def _format_exception_info(self, exception_info_tuple):
        exctype, value, tb = exception_info_tuple
        # Skip test runner traceback levels
        while tb and self.__is_relevant_tb_level(tb):
            tb = tb.tb_next
        if exctype is AssertionError:
            # Skip testify.assertions traceback levels
            length = self.__count_relevant_tb_levels(tb)
            return self.traceback_formatter(exctype, value, tb, length)

        if not tb:
            return "Exception: %r (%r)" % (exctype, value)

        return self.traceback_formatter(exctype, value, tb)

    def __is_relevant_tb_level(self, tb):
        return tb.tb_frame.f_globals.has_key('__testify')

    def __count_relevant_tb_levels(self, tb):
        length = 0
        while tb and not self.__is_relevant_tb_level(tb):
            length += 1
            tb = tb.tb_next
        return length


class TextTestLogger(TestLoggerBase):
    traceback_formatter = fancy_tb_formatter
    def __init__(self, options, stream=sys.stdout):
        super(TextTestLogger, self).__init__(options)

        # Checking for color support isn't as fun as we might hope.  We're
        # going to use the command 'tput colors' to get a list of colors
        # supported by the shell. But of course we if this fails terribly,
        # we'll want to just fall back to no colors
        self.use_color = False
        if sys.stdin.isatty():
            try:
                output = subprocess.Popen(["tput", "colors"], stdout=subprocess.PIPE).communicate()[0]
                if int(output.strip()) >= 8:
                    self.use_color = True
            except Exception, e:
                _log.debug("Failed to find color support: %r", e)

    def write(self, message):
        """Write a message to the output stream, no trailing newline"""
        self.stream.write(message)
        self.stream.flush()

    def writeln(self, message):
        """Write a message and append a newline"""
        self.stream.write("%s\n" % message)
        self.stream.flush()

    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(30, 38)

    def _colorize(self, message, color = CYAN):
        if not color or not self.use_color:
            return message
        else:
            start_color = chr(0033) + '[1;%sm' % color
            end_color = chr(0033) + '[m'
            return start_color + message + end_color

    def report_test_name(self, test_method):
        _log.info("running: %s", self._format_test_method_name(test_method))
        if self.options.verbosity >= VERBOSITY_VERBOSE:
            self.write("%s ... " % self._format_test_method_name(test_method))

    def report_test_result(self, result):
        if self.options.verbosity > VERBOSITY_SILENT:

            if result.success:
                if not result.unexpected_success:
                    _log.info("success: %s", self._format_test_method_name(result.test_method))
                    if self.options.verbosity == VERBOSITY_NORMAL:
                        self.write(self._colorize('.', self.GREEN))
                    else:
                        self.writeln("%s in %s" % (self._colorize('ok', self.GREEN), result.normalized_run_time()))
                else:
                    _log.info("unexpected success: %s", self._format_test_method_name(result.test_method))
                    if self.options.verbosity == VERBOSITY_NORMAL:
                        self.write(self._colorize('.', self.RED))
                    else:
                        self.writeln("%s in %s" % (self._colorize('UNEXPECTED SUCCESS', self.RED), result.normalized_run_time()))

            elif result.failure:
                if result.test_method.im_class.in_suite(result.test_method, 'expected-failure'):
                    _log.error("fail (expected): %s", self._format_test_method_name(result.test_method), exc_info=result.exception_info)
                    if self.options.verbosity == VERBOSITY_NORMAL:
                        self.write(self._colorize('f', self.RED))
                    else:
                        self.writeln("%s in %s" % (self._colorize("FAIL (EXPECTED)", self.RED), result.normalized_run_time()))
                else:
                    _log.error("fail: %s", self._format_test_method_name(result.test_method), exc_info=result.exception_info)
                    if self.options.verbosity == VERBOSITY_NORMAL:
                        self.write(self._colorize('F', self.RED))
                    else:
                        self.writeln("%s in %s" % (self._colorize("FAIL", self.RED), result.normalized_run_time()))

            elif result.error:
                if result.test_method.im_class.in_suite(result.test_method, 'expected-failure'):
                    _log.error("error (expected): %s", self._format_test_method_name(result.test_method), exc_info=result.exception_info)
                    if self.options.verbosity == VERBOSITY_NORMAL:
                        self.write(self._colorize('e', self.RED))
                    else:
                        self.writeln("%s in %s" % (self._colorize("ERROR (EXPECTED)", self.RED), result.normalized_run_time()))
                else:
                    _log.error("error: %s", self._format_test_method_name(result.test_method), exc_info=result.exception_info)
                    if self.options.verbosity == VERBOSITY_NORMAL:
                        self.write(self._colorize('E', self.RED))
                    else:
                        self.writeln("%s in %s" % (self._colorize("ERROR", self.RED), result.normalized_run_time()))

            elif result.incomplete:
                _log.info("incomplete: %s", self._format_test_method_name(result.test_method))
                if self.options.verbosity == VERBOSITY_NORMAL:
                    self.write(self._colorize('-', self.YELLOW))
                else:
                    self.writeln(self._colorize('INCOMPLETE', self.YELLOW))

            else:
                _log.info("unknown: %s", self._format_test_method_name(result.test_method))
                if self.options.verbosity == VERBOSITY_NORMAL:
                    self.write('?')
                else:
                    self.writeln('UNKNOWN')

    def heading(self, *messages):
        self.writeln("")
        self.writeln("=" * 72)
        for line in messages:
            self.writeln(line)

    def failure(self, result):
        self.writeln("")
        self.writeln("=" * 72)
        # self.write("%s: " % self._colorize(('FAIL' if result.failure else 'ERROR'), self.RED))
        self.writeln(self._format_test_method_name(result.test_method))
        self.writeln(''.join(self._format_exception_info(result.exception_info)))
        self.writeln('=' * 72)
        self.writeln("")

    def report_stats(self, test_case_count, **results):
        successful = results.get('successful', [])
        unexpected_success = results.get('unexpected_success', [])
        failed = results.get('failed', [])
        incomplete = results.get('incomplete', [])
        unknown = results.get('unknown', [])

        test_method_count = sum(len(bucket) for bucket in results.values())
        test_word = "test" if test_method_count == 1 else "tests"
        case_word = "case" if test_case_count == 1 else "cases"
        unexpected_failed = [result for result in failed if not result.test_method.im_class.in_suite(result.test_method, 'expected-failure')]
        overall_success = not unexpected_failed and not unknown and not incomplete

        self.writeln('')
        status_string = self._colorize("PASSED", self.GREEN) if overall_success else self._colorize("FAILED", self.RED)
        self.write("%s.  " % status_string)
        self.write("%d %s / %d %s: " % (test_method_count, test_word, test_case_count, case_word))

        passed_string = self._colorize("%d passed" % len(successful+unexpected_success), (self.GREEN if len(successful+unexpected_success) else None))
        passed_string += self._colorize(" (%d unexpected)" % len(unexpected_success), (self.RED if len(unexpected_success) else None))

        failed_string = self._colorize("%d failed" % len(failed), (self.RED if len(failed) else None))
        failed_string += self._colorize(" (%d expected)" % (len(failed) - len(unexpected_failed)), (self.RED if len(unexpected_failed) else None))

        self.write("%s, %s.  " % (passed_string, failed_string))

        total_test_time = reduce(
            operator.add,
            (result.run_time for result in (successful+unexpected_success+failed+incomplete)),
            datetime.timedelta())
        self.writeln("(Total test time %.2fs)" % (total_test_time.seconds + total_test_time.microseconds / 1000000.0))

class HTMLTestLogger(TextTestLogger):
    traceback_formatter = staticmethod(traceback.format_exception)

    def writeln(self, message):
        """Write a message and append a newline"""
        self.stream.write("%s<br />" % message)
        self.stream.flush()

    BLACK   = "#000"
    BLUE    = "#00F"
    GREEN   = "#0F0"
    CYAN    = "#0FF"
    RED     = "#F00"
    MAGENTA = "#F0F"
    YELLOW  = "#FF0"
    WHITE   = "#FFF"

    def _colorize(self, message, color = CYAN):
        if not color:
            return message
        else:
            start_color = "<span style='color:%s'>" % color
            end_color = "</span>"
            return start_color + message + end_color

class ColorlessTextTestLogger(TextTestLogger):
    traceback_formatter = staticmethod(traceback.format_exception)

    def _colorize(self, message, color=None):
        return message


class TestResultGrabberHandler(logging.Handler):
    """Logging handler to store log message during a test run"""
    def emit(self, record):
        raise Exception(repr(record))
