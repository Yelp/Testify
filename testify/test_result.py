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

class TestResult(object):
    def __init__(self, test_method):
        super(TestResult, self).__init__()
        self.test_method = test_method
        self.test_method_name = test_method.__name__
        self.success = self.failure = self.error = self.interrupted = None
        self.run_time = self.start_time = self.end_time = None
        self.exception_info = None
        self.complete = False

    def start(self):
        self.start_time = datetime.datetime.now()

    def _complete(self):
        self.complete = True
        self.end_time = datetime.datetime.now()
        self.run_time = self.end_time - self.start_time

    def end_in_failure(self, exception_info):
        if not self.complete:
            self._complete()
            self.failure = True
            self.exception_info = exception_info

    def end_in_error(self, exception_info):
        if not self.complete:
            self._complete()
            self.error = True
            self.exception_info = exception_info

    def end_in_success(self):
        if not self.complete:
            self._complete()
            self.success = True

    def end_in_interruption(self, exception_info):
        if not self.complete:
            self._complete()
            self.interrupted = True
            self.exception_info = exception_info

    def to_dict(self):
        return {
            'run_time' : self.run_time,
            'normalized_run_time' : None if not self.run_time else "%.2fs" % (self.run_time.seconds + (self.run_time.microseconds / 1000000.0)),
            'complete': self.complete,
            'success' : self.success,
            'failure' : self.failure,
            'error' : self.error,
            'interrupted' : self.interrupted,
            'exception_info' : self.exception_info,
            'method' : {
                'name' : self.test_method.__name__,
                'module' : self.test_method.__module__,
                'class' : self.test_method.im_class.__name__,
                'fixture_type' : None if not self.test_method.im_self.is_fixture_method(self.test_method) else self.test_method._fixture_type,
            }
        }
