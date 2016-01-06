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
import json
import logging

from testify import test_reporter


class TestCaseJSONReporter(test_reporter.TestReporter):
    def __init__(self, *args, **kwargs):
        super(TestCaseJSONReporter, self).__init__(*args, **kwargs)

        # Time to open a log file
        self.log_file = open(self.options.test_case_json_results, "a")
        # We also want to track log output
        self.log_hndl = None
        self._reset_logging()

    def _reset_logging(self):
        root = logging.getLogger('')
        if self.log_hndl:
            # Remove it if we already have one
            root.removeHandler(self.log_hndl)

    def test_case_complete(self, result):
        self.log_file.write(json.dumps(result))
        self.log_file.write("\n")

        self._reset_logging()

    def report(self):
        self.log_file.write("RUN COMPLETE\n")
        self.log_file.close()
        return True


# Hooks for plugin system
def add_command_line_options(parser):
    parser.add_option(
        "--test-case-results",
        action="store",
        dest="test_case_json_results",
        type="string",
        default=None,
        help="Store test results in json format",
    )


def build_test_reporters(options):
    if options.test_case_json_results:
        return [TestCaseJSONReporter(options)]
    else:
        return []
