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
import logging
import time

try:
    import simplejson as json
except ImportError:
    import json

from testify import test_reporter
from testify.utils import exception

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
            self.log_hndl = ResultLogHandler(logging.Handler)
            self.log_hndl.setLevel(self.options.verbosity)
            self.log_hndl.setFormatter(logging.Formatter('%(asctime)s\t%(name)-12s: %(levelname)-8s %(message)s'))
            root.addHandler(self.log_hndl)

    def test_complete(self, test_case, result):
        """Called when a test case is complete"""
        out_result = {}

        if self.options.label:
            out_result['label'] = self.options.label
        if self.options.extra_json_info:
            if not hasattr(self.options, 'parsed_extra_json_info'):
                self.options.parsed_extra_json_info = json.loads(self.options.extra_json_info)
            out_result.update(self.options.parsed_extra_json_info)
        if self.options.bucket is not None:
            out_result['bucket'] = self.options.bucket
        if self.options.bucket_count is not None:
            out_result['bucket_count'] = self.options.bucket_count

        out_result['name'] = '%s %s.%s' % (result.test_method.im_class.__module__, result.test_method.im_class.__name__, result.test_method.__name__)
        out_result['module'] = '%s' % result.test_method.im_class.__module__
        out_result['start_time'] = time.mktime(result.start_time.timetuple())
        out_result['end_time'] = time.mktime(result.end_time.timetuple())
        out_result['run_time'] = result.run_time.seconds + float(result.run_time.microseconds) / 1000000

        # Classify the test
        if test_case.is_fixture_method(result.test_method):
            out_result['type'] = 'fixture'
        elif test_case.method_excluded(result.test_method):
            out_result['type'] = 'excluded'
        else:
            out_result['type'] = 'test'

        out_result['success'] = bool(result.success)
        if not result.success:
            out_result['tb'] = exception.format_exception_info(result.exception_info)
            out_result['error'] = str(out_result['tb'][-1]).strip()
            if self.log_hndl:
                out_result['log'] = self.log_hndl.results()

        self.log_file.write(json.dumps(out_result))
        self.log_file.write("\n")

        self._reset_logging()

    def report(self):
        self.log_file.write("RUN COMPLETE\n")
        self.log_file.close()
        return True


# Hooks for plugin system

def add_command_line_options(parser):
    parser.add_option("--json-results", action="store", dest="json_results", type="string", default=None, help="Store test results in json format")
    parser.add_option("--json-results-logging", action="store_true", dest="json_results_logging", default=False, help="Store log output for failed test results in json")
    parser.add_option("--extra-json-info", action="store", dest="extra_json_info", type="string", help="json containing some extra info to be stored")

def build_test_reporters(options):
    if options.json_results:
        return [JSONReporter(options)]
    else:
        return []
