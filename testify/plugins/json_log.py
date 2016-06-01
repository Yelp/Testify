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


class ResultLogHandler(logging.Handler):
    """Log Handler to collect log output during a test run"""

    def __init__(self, *args, **kwargs):
        logging.Handler.__init__(self, *args, **kwargs)

        self.records = []

    def emit(self, record):
        self.records.append(record)

    def results(self):
        return [self.formatter.format(rec) for rec in self.records]


class JSONReporter(test_reporter.TestReporter):
    def __init__(self, *args, **kwargs):
        super(JSONReporter, self).__init__(*args, **kwargs)

        # Time to open a log file
        self.log_file = open(self.options.json_results, "a")

        # We also want to track log output
        self.log_hndl = None
        self._reset_logging()

    def _reset_logging(self):
        root = logging.getLogger('')
        if self.log_hndl:
            # Remove it if we already have one
            root.removeHandler(self.log_hndl)

        # Create a new one
        if self.options.json_results_logging:
            self.log_hndl = ResultLogHandler()
            self.log_hndl.setLevel(self.options.verbosity)
            self.log_hndl.setFormatter(logging.Formatter('%(asctime)s\t%(name)-12s: %(levelname)-8s %(message)s'))
            root.addHandler(self.log_hndl)

    def test_complete(self, result):
        """Called when a test case is complete"""

        if self.options.label:
            result['label'] = self.options.label
        if self.options.extra_json_info:
            if not hasattr(self.options, 'parsed_extra_json_info'):
                self.options.parsed_extra_json_info = json.loads(self.options.extra_json_info)
            result.update(self.options.parsed_extra_json_info)

        if not result['success']:
            if self.log_hndl:
                result['log'] = self.log_hndl.results()

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
        "--json-results",
        action="store",
        dest="json_results",
        type="string",
        default=None,
        help="Store test results in json format",
    )
    parser.add_option(
        "--json-results-logging",
        action="store_true",
        dest="json_results_logging",
        default=False,
        help="Store log output for failed test results in json",
    )
    parser.add_option(
        "--extra-json-info",
        action="store",
        dest="extra_json_info",
        type="string",
        help="json containing some extra info to be stored",
    )


def build_test_reporters(options):
    if options.json_results:
        return [JSONReporter(options)]
    else:
        return []
