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


"""This module contains the TestResult class, each instance of which holds status information for a single test method."""
__testify = 1
import datetime
import sys
import time
import traceback

from testify.utils import inspection

#If IPython is available, use it for fancy color traceback formatting
try:
    try:
        # IPython >= 0.11
        from IPython.core.ultratb import ListTB
        _hush_pyflakes = [ListTB]
        del _hush_pyflakes
    except ImportError:
        # IPython < 0.11
        from IPython.ultraTB import ListTB

    list_tb = ListTB(color_scheme='Linux')
    def fancy_tb_formatter(etype, value, tb, length=None):
        tb = traceback.extract_tb(tb, limit=length)
        return list_tb.text(etype, value, tb, context=0)
except ImportError:
    fancy_tb_formatter = None

def plain_tb_formatter(etype, value, tb, length=None):
    # We want our formatters to return a string.
    return ''.join(traceback.format_exception(etype, value, tb, length))

class TestResult(object):
    debug = False

    def __init__(self, test_method, runner_id=None):
        super(TestResult, self).__init__()
        self.test_method = test_method
        self.test_method_name = test_method.__name__
        self.success = self.failure = self.error = self.interrupted = None
        self.run_time = self.start_time = self.end_time = None
        self.exception_infos = []
        self.complete = False
        self.previous_run = None
        self.runner_id = runner_id

    @property
    def exception_info(self):
        raise AttributeError('The exception_info attribute has been replaced with the .exception_infos list. Please update your code.')

    def start(self, previous_run=None):
        self.previous_run = previous_run
        self.start_time = datetime.datetime.now()

    def record(self, function):
        """Excerpted code for executing a block of code that might raise an
        exception, requiring us to update a result object.

        Return value is a boolean describing whether the block was successfully
        executed without exceptions.
        """
        try:
            function()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception, exception:
            # some code may want to use an alternative exc_info for an exception
            # (for instance, in an event loop). You can signal an alternative
            # stack to use by adding a _testify_exc_tb attribute to the
            # exception object
            if hasattr(exception, '_testify_exc_tb'):
                exc_info = (type(exception), exception, exception._testify_exc_tb)
            else:
                exc_info = sys.exc_info()

            self.end_in_failure(exc_info)

            if self.debug:
                self._postmortem(exc_info)
            return False
        else:
            return True

    def _postmortem(self, exc_info):
        _, _, traceback = exc_info
        print "\nDEBUGGER"
        print self.format_exception_info()
        try:
            import ipdb
            detected_postmortem_tool = ipdb.post_mortem
        except ImportError:
            import pdb
            detected_postmortem_tool = pdb.post_mortem
        detected_postmortem_tool(traceback)

    def _complete(self):
        self.complete = True
        self.end_time = datetime.datetime.now()
        self.run_time = self.end_time - self.start_time

    def end_in_failure(self, exception_info):
        if not self.complete:
            self._complete()

        self.success = False

        if isinstance(exception_info[1], AssertionError):
            # test failure, kinda expect these vs. unknown errors
            self.failure = True
        else:
            self.error = True

        self.exception_infos.append(exception_info)

    def end_in_success(self):
        if not self.complete:
            self._complete()
            self.success = True

    def end_in_interruption(self, exception_info):
        if not self.complete:
            self._complete()
            self.interrupted = True
            self.exception_infos.append(exception_info)

    def __make_multi_error_message(self, formatter):
        result = []
        for exception_info in self.exception_infos:
            exctype, value, tb = exception_info
            part = formatter(exctype, value, tb)
            result.append(part)

        if len(result) == 1:
            return result[0]
        else:
            # Meant to match the python3 multiple-exception support:
            #   http://docs.python.org/3.1/reference/simple_stmts.html#the-raise-statement
            return '\nDuring handling of the above exception, another exception occurred:\n\n'.join(result)

    def format_exception_info(self, pretty=False):
        if not self.exception_infos:
            return None

        tb_formatter = fancy_tb_formatter if (pretty and fancy_tb_formatter) else plain_tb_formatter

        def is_relevant_tb_level(tb):
            if tb.tb_frame.f_globals.has_key('__testify'):
                # nobody *wants* to read testify
                return False
            else:
                return True

        def count_relevant_tb_levels(tb):
            # count up to the *innermost* relevant frame
            length = 0
            relevant = 0
            while tb:
                length += 1
                if is_relevant_tb_level(tb):
                    relevant = length
                tb = tb.tb_next
            return relevant

        def formatter(exctype, value, tb):
            # Skip test runner traceback levels at the top.
            while tb and not is_relevant_tb_level(tb):
                tb = tb.tb_next

            if exctype is AssertionError:
                # Skip testify.assertions traceback levels at the bottom.
                length = count_relevant_tb_levels(tb)
                return tb_formatter(exctype, value, tb, length)
            elif not tb:
                return "Exception: %r (%r)" % (exctype, value)
            else:
                return tb_formatter(exctype, value, tb)

        return self.__make_multi_error_message(formatter)

    def format_exception_only(self):
        def formatter(exctype, value, tb):
            return ''.join(traceback.format_exception_only(exctype, value))

        return self.__make_multi_error_message(formatter)

    def to_dict(self):
        return {
            'previous_run' : self.previous_run,
            'start_time' : time.mktime(self.start_time.timetuple()) if self.start_time else None,
            'end_time' : time.mktime(self.end_time.timetuple()) if self.end_time else None,
            'run_time' : (self.run_time.seconds + float(self.run_time.microseconds) / 1000000) if self.run_time else None,
            'normalized_run_time' : None if not self.run_time else "%.2fs" % (self.run_time.seconds + (self.run_time.microseconds / 1000000.0)),
            'complete': self.complete,
            'success' : self.success,
            'failure' : self.failure,
            'error' : self.error,
            'interrupted' : self.interrupted,
            'exception_info' : self.format_exception_info(),
            'exception_info_pretty' : self.format_exception_info(pretty=True),
            'exception_only' : self.format_exception_only(),
            'runner_id' : self.runner_id,
            'method' : {
                'module' : self.test_method.im_class.__module__,
                'class' : self.test_method.im_class.__name__,
                'name' : self.test_method.__name__,
                'full_name' : '%s %s.%s' % (self.test_method.im_class.__module__, self.test_method.im_class.__name__, self.test_method.__name__),
                'fixture_type' : None if not inspection.is_fixture_method(self.test_method) else self.test_method._fixture_type,
            }
        }

# vim: set ts=4 sts=4 sw=4 et:
