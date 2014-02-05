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
from __future__ import with_statement

from collections import defaultdict
from optparse import OptionParser
import os
import pwd
import socket
import sys
import logging
import imp

import testify
from testify import test_logger
from testify.test_runner import TestRunner

ACTION_RUN_TESTS = 0
ACTION_LIST_SUITES = 1
ACTION_LIST_TESTS = 2

DEFAULT_PLUGIN_PATH = os.path.join(os.path.split(__file__)[0], 'plugins')

log = logging.getLogger('testify')

def get_bucket_overrides(filename):
    """Returns a map from test class name to test bucket.

    test class name: {test module}.{classname}
    test bucket: int
    """
    ofile = open(filename)
    overrides = {}
    for line in ofile.readlines():
        if line.startswith('#'):
            continue
        if line.strip() == '':
            continue
        test_module_and_class, bucket = line.strip().split(',')
        overrides[test_module_and_class] = int(bucket)
    ofile.close()
    return overrides

def load_plugins():
    """Load any plugin modules

    We load plugin modules based on directories provided to us by the environment, as well as a default in our own folder.

    Returns a list of module objects
    """
    # This function is a little wacky, doesn't seem like we SHOULD have to do all this just to get the behavior we want.
    # The idea will be to check out the directory contents and pick up any files that seem to match what python knows how to
    # import.

    # To properly load the module, we'll need to identify what type it is by the file extension
    suffix_map = {}
    for suffix in imp.get_suffixes():
        suffix_map[suffix[0]] = suffix

    plugin_directories = [DEFAULT_PLUGIN_PATH]
    if 'TESTIFY_PLUGIN_PATH' in os.environ:
        plugin_directories += os.environ['TESTIFY_PLUGIN_PATH'].split(':')

    plugin_modules = []
    for plugin_path in plugin_directories:
        for file_name in os.listdir(plugin_path):

            # For any file that we know how to load, try to import it
            if any(file_name.endswith('.py') and not file_name.startswith('.') for suffix in suffix_map.iterkeys()):
                full_file_path = os.path.join(plugin_path, file_name)
                mod_name, suffix = os.path.splitext(file_name)

                with open(full_file_path, "r") as file:
                    try:
                        plugin_modules.append(imp.load_module(mod_name, file, full_file_path, suffix_map.get(suffix)))
                    except TypeError:
                        continue
                    except ImportError, e:
                        print >>sys.stderr, "Failed to import plugin %s: %r" % (full_file_path, e)
                    except Exception, e:
                        raise Exception('whaa?: %r' % e)
    return plugin_modules


def parse_test_runner_command_line_args(plugin_modules, args):
    """Parse command line args for the TestRunner to determine verbosity and other stuff"""
    parser = OptionParser(usage="%prog <test path> [options]", version="%%prog %s" % testify.__version__)

    parser.set_defaults(verbosity=test_logger.VERBOSITY_NORMAL)
    parser.add_option("-s", "--silent", action="store_const", const=test_logger.VERBOSITY_SILENT, dest="verbosity")
    parser.add_option("-v", "--verbose", action="store_const", const=test_logger.VERBOSITY_VERBOSE, dest="verbosity")
    parser.add_option("-d", "--ipdb", action="store_true", dest="debugger", help="Enter post mortem debugging mode with ipdb in the case of an exception thrown in a test method or fixture method.")

    parser.add_option("-i", "--include-suite", action="append", dest="suites_include", type="string", default=[])
    parser.add_option("-x", "--exclude-suite", action="append", dest="suites_exclude", type="string", default=[])
    parser.add_option("-q", "--require-suite", action="append", dest="suites_require", type="string", default=[])

    parser.add_option("--list-suites", action="store_true", dest="list_suites")
    parser.add_option("--list-tests", action="store_true", dest="list_tests")

    parser.add_option("--label", action="store", dest="label", type="string", help="label for this test run")

    parser.add_option("--bucket", action="store", dest="bucket", type="int")
    parser.add_option("--bucket-count", action="store", dest="bucket_count", type="int")
    parser.add_option("--bucket-overrides-file", action="store", dest="bucket_overrides_file", default=None)
    parser.add_option("--bucket-salt", action="store", dest="bucket_salt", default=None)

    parser.add_option("--summary", action="store_true", dest="summary_mode")
    parser.add_option("--no-color", action="store_true", dest="disable_color", default=bool(not os.isatty(sys.stdout.fileno())))

    parser.add_option("--log-file", action="store", dest="log_file", type="string", default=None)
    parser.add_option("--log-level", action="store", dest="log_level", type="string", default="INFO")
    parser.add_option('--print-log', action="append", dest="print_loggers", type="string", default=[], help="Direct logging output for these loggers to the console")

    parser.add_option('--serve', action="store", dest="serve_port", type="int", default=None, help="Run in server mode, listening on this port for testify clients.")
    parser.add_option('--connect', action="store", dest="connect_addr", type="string", default=None, metavar="HOST:PORT", help="Connect to a testify server (testify --serve) at this HOST:PORT")
    parser.add_option('--revision', action="store", dest="revision", type="string", default=None, help="With --serve, refuses clients that identify with a different or no revision. In client mode, sends the revision number to the server for verification.")
    parser.add_option('--retry-limit', action="store", dest="retry_limit", type="int", default=60, help="Number of times to try connecting to the server before exiting.")
    parser.add_option('--retry-interval', action="store", dest="retry_interval", type="int", default=2, help="Interval, in seconds, between trying to connect to the server.")
    parser.add_option('--reconnect-retry-limit', action="store", dest="reconnect_retry_limit", type="int", default=5, help="Number of times to try reconnecting to the server before exiting if we have previously connected.")
    parser.add_option('--disable-requeueing', action="store_true", dest="disable_requeueing", help="Disable re-queueing/re-running failed tests on a different builder.")

    parser.add_option('--failure-limit', action="store", dest="failure_limit", type="int", default=None, help="Quit after this many test failures.")
    parser.add_option('--runner-timeout', action="store", dest="runner_timeout", type="int", default=300, help="How long to wait to wait for activity from a test runner before requeuing the tests it has checked out.")
    parser.add_option('--server-timeout', action="store", dest="server_timeout", type="int", default=300, help="How long to wait after the last activity from any test runner before shutting down.")

    parser.add_option('--server-shutdown-delay', action='store', dest='shutdown_delay_for_connection_close', type="float", default=0.01, help="How long to wait (in seconds) for data to finish writing to sockets before shutting down the server.")
    parser.add_option('--server-shutdown-delay-outstanding-runners', action='store', dest='shutdown_delay_for_outstanding_runners', type='int', default=5, help="How long to wait (in seconds) for all clients to check for new tests before shutting down the server.")

    parser.add_option('--runner-id', action="store", dest="runner_id", type="string", default="%s-%d" % (socket.gethostname(), os.getpid()), help="With --connect, an identity passed to the server on each request. Passed to the server's test reporters. Defaults to <HOST>-<PID>.")

    parser.add_option('--replay-json', action="store", dest="replay_json", type="string", default=None, help="Instead of discovering and running tests, read a file with one JSON-encoded test result dictionary per line, and report each line to test reporters as if we had just run that test.")
    parser.add_option('--replay-json-inline', action="append", dest="replay_json_inline", type="string", metavar="JSON_OBJECT", help="Similar to --replay-json, but allows result objects to be passed on the command line. May be passed multiple times. If combined with --replay-json, inline results get reported first.")

    parser.add_option('--rerun-test-file', action="store", dest="rerun_test_file", type="string", default=None, help="Rerun tests listed in FILE in order. One test per line, in the format 'path.to.class ClassName.test_method_name'. Consecutive tests in the same class will be run on the same test class instance.")

    # Add in any additional options
    for plugin in plugin_modules:
        if hasattr(plugin, 'add_command_line_options'):
            plugin.add_command_line_options(parser)

    (options, args) = parser.parse_args(args)
    if len(args) < 1 and not (options.connect_addr or options.rerun_test_file or options.replay_json or options.replay_json_inline):
        parser.error("Test path required unless --connect or --rerun-test-file specified.")

    if options.connect_addr and options.serve_port:
        parser.error("--serve and --connect are mutually exclusive.")

    test_path, module_method_overrides = _parse_test_runner_command_line_module_method_overrides(args)

    if pwd.getpwuid(os.getuid()).pw_name == 'buildbot':
        options.disable_color = True

    if options.list_suites:
        runner_action = ACTION_LIST_SUITES
    elif options.list_tests:
        runner_action = ACTION_LIST_TESTS
    else:
        runner_action = ACTION_RUN_TESTS


    test_runner_args = {
        'debugger': options.debugger,
        'suites_include': options.suites_include,
        'suites_exclude': options.suites_exclude,
        'suites_require': options.suites_require,
        'failure_limit' : options.failure_limit,
        'module_method_overrides': module_method_overrides,
        'options': options,
        'plugin_modules': plugin_modules
    }

    return runner_action, test_path, test_runner_args, options

def _parse_test_runner_command_line_module_method_overrides(args):
    """Parse a set of positional args (returned from an OptionParser probably) for specific modules or test methods.
    eg/ > python some_module_test.py SomeTestClass.some_test_method
    """

    test_path = args[0] if args else None

    module_method_overrides = defaultdict(set)
    for arg in args[1:]:
        module_path_components = arg.split('.')
        module_name = module_path_components[0]
        method_name = module_path_components[1] if len(module_path_components) > 1 else None
        if method_name:
            module_method_overrides[module_name].add(method_name)
        else:
            module_method_overrides[module_name] = None

    return test_path, module_method_overrides


class TestProgram(object):

    def __init__(self, command_line_args=None):
        """Initialize and run the test with the given command_line_args
            command_line_args will be passed to parser.parse_args
        """
        self.plugin_modules = load_plugins()
        command_line_args = command_line_args or sys.argv[1:]
        self.runner_action, self.test_path, self.test_runner_args, self.other_opts = parse_test_runner_command_line_args(
            self.plugin_modules,
            command_line_args
        )

        # allow plugins to modify test program
        for plugin_mod in self.plugin_modules:
            if hasattr(plugin_mod, "prepare_test_program"):
                plugin_mod.prepare_test_program(self.other_opts, self)

    def get_reporters(self, options, plugin_modules):
        reporters = []
        if options.disable_color:
            reporters.append(test_logger.ColorlessTextTestLogger(options))
        else:
            reporters.append(test_logger.TextTestLogger(options))

        for plugin in plugin_modules:
            if hasattr(plugin, "build_test_reporters"):
                reporters += plugin.build_test_reporters(options)
        return reporters

    def run(self):
        """Run testify, return True on success, False on failure."""
        self.setup_logging(self.other_opts)

        bucket_overrides = {}
        if self.other_opts.bucket_overrides_file:
            bucket_overrides = get_bucket_overrides(self.other_opts.bucket_overrides_file)

        if self.other_opts.serve_port:
            from test_runner_server import TestRunnerServer
            test_runner_class = TestRunnerServer
            self.test_runner_args['serve_port'] = self.other_opts.serve_port
        elif self.other_opts.connect_addr:
            from test_runner_client import TestRunnerClient
            test_runner_class = TestRunnerClient
            self.test_runner_args['connect_addr'] = self.other_opts.connect_addr
            self.test_runner_args['runner_id'] = self.other_opts.runner_id
        elif self.other_opts.replay_json or self.other_opts.replay_json_inline:
            from test_runner_json_replay import TestRunnerJSONReplay
            test_runner_class = TestRunnerJSONReplay
            self.test_runner_args['replay_json'] = self.other_opts.replay_json
            self.test_runner_args['replay_json_inline'] = self.other_opts.replay_json_inline
        elif self.other_opts.rerun_test_file:
            from test_rerunner import TestRerunner
            test_runner_class = TestRerunner
            self.test_runner_args['rerun_test_file'] = self.other_opts.rerun_test_file
        else:
            test_runner_class = TestRunner

        # initialize reporters 
        self.test_runner_args['test_reporters'] = self.get_reporters(
            self.other_opts, self.test_runner_args['plugin_modules']
        )

        runner = test_runner_class(
            self.test_path,
            bucket_overrides=bucket_overrides,
            bucket_count=self.other_opts.bucket_count,
            bucket_salt=self.other_opts.bucket_salt,
            bucket=self.other_opts.bucket,
            **self.test_runner_args
        )

        if self.runner_action == ACTION_LIST_SUITES:
            runner.list_suites()
            return True
        elif self.runner_action == ACTION_LIST_TESTS:
            runner.list_tests()
            return True
        elif self.runner_action == ACTION_RUN_TESTS:
            label_text = ""
            bucket_text = ""
            if self.other_opts.label:
                label_text = " " + self.other_opts.label
            if self.other_opts.bucket_count:
                salt_info =  (' [salt: %s]' % self.other_opts.bucket_salt) if self.other_opts.bucket_salt else ''
                bucket_text = " (bucket %d of %d%s)" % (self.other_opts.bucket, self.other_opts.bucket_count, salt_info)
            log.info("starting test run%s%s", label_text, bucket_text)

            # Allow plugins to modify the test runner.
            for plugin_mod in self.test_runner_args['plugin_modules']:
                if hasattr(plugin_mod, "prepare_test_runner"):
                    plugin_mod.prepare_test_runner(self.test_runner_args['options'], runner)

            return runner.run()

    def setup_logging(self, options):
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
        console.setLevel(logging.WARNING)
        root_logger.addHandler(console)

        if options.log_file:
            handler = logging.FileHandler(options.log_file, "a")
            handler.setFormatter(logging.Formatter('%(asctime)s\t%(name)-12s: %(levelname)-8s %(message)s'))

            log_level = getattr(logging, options.log_level)
            handler.setLevel(log_level)

            root_logger.addHandler(handler)

        if options.print_loggers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(name)-12s: %(message)s')
            console.setFormatter(formatter)

            for logger_name in options.print_loggers:
                logging.getLogger(logger_name).addHandler(handler)


def main():
    sys.exit(not TestProgram().run())


if __name__ == "__main__":
    main()
