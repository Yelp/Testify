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


class TestReporter(object):
    """Base interface for tracking results of test runs

    A TestReporter is configured as a callback for each test case by test_runner.
    """

    def __init__(self, options):
        """Constructor

        Args -
            options - The result of  OptionParser which contains, as attributes, all the options for the running program.
        """
        self.options = options

    def test_start(self, result):
        """Called when a test method is being run. Gets passed a TestResult dict which should not be complete."""
        pass

    def test_complete(self, result):
        """Called when a test method is complete. result is a TestResult dict which should be complete."""
        pass

    def test_discovery_failure(self, exc):
        """Called when there was a failure during test discovery. exc is the exception object generated during the error."""

    def class_setup_start(self, result):
        """Called when a class_setup or the first half of a class_setup_teardown starts"""
        pass

    def class_setup_complete(self, result):
        """Called when a class_setup or the first half of a class_setup_teardown finishes"""
        pass

    def class_teardown_start(self, result):
        """Called when a class_teardown or the second half of a class_setup_teardown starts"""
        pass

    def class_teardown_complete(self, result):
        """Called when a class_teardown or the second half of a class_setup_teardown finishes"""
        pass

    def test_case_start(self, result):
        """Called when a test case is being run. Gets passed the special "run" method as a TestResult."""
        pass

    def test_case_complete(self, result):
        """Called when a test case and all of its fixtures have been run."""
        pass

    def report(self):
        """Called at the end of the test run to report results

        Should return a bool to indicate if the reporter thinks the test run was successful
        """
        return True

# vim: set ts=4 sts=4 sw=4 et:
