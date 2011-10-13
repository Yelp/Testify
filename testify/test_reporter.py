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

    def test_start(self, test_case, method):
        """Called when a test method is being run."""
        pass

    def test_complete(self, test_case, result):
        """Called when a test case is complete"""
        pass

    def report(self):
        """Called at the end of the test run to report results

		Should return a bool to indicate if the reporter thinks the test run was successful
		"""
        return True

