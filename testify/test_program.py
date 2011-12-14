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

    parser.add_option('--serve', action="store", dest="serve_port", type="int", default=None)
    parser.add_option('--connect', action="store", dest="connect_addr", type="string", default=None)
    parser.add_option('--revision', action="store", dest="revision", type="string", default=None)

    parser.add_option('--failure-limit', action="store", dest="failure_limit", type="int", default=None)
    parser.add_option('--runner-timeout', action="store", dest="runner_timeout", type="int", default=300)
    parser.add_option('--runner-id', action="store", dest="runner_id", type="string", default=None)

    parser.add_option('--replay-json', action="store", dest="replay_json", type="string", default=None)
    parser.add_option('--replay-json-inline', action="append", dest="replay_json_inline", type="string")

    # Add in any additional options
    for plugin in plugin_modules:
        if hasattr(plugin, 'add_command_line_options'):
            plugin.add_command_line_options(parser)

    (options, args) = parser.parse_args(args)
    if len(args) < 1:
        parser.error("Test path required")

    if options.connect_addr and options.serve_port:
        parser.error("--serve and --connect are mutually exclusive.")

    if options.connect_addr and not options.runner_id:
        parser.error("--runner-id is required when --connect address is specified.")

    test_path, module_method_overrides = _parse_test_runner_command_line_module_method_overrides(args)

    if pwd.getpwuid(os.getuid()).pw_name == 'buildbot':
        options.disable_color = True

    if options.list_suites:
        runner_action = ACTION_LIST_SUITES
    elif options.list_tests:
        runner_action = ACTION_LIST_TESTS
    else:
        runner_action = ACTION_RUN_TESTS

    reporters = []
    if options.disable_color:
        reporters.append(test_logger.ColorlessTextTestLogger(options))
    else:
        reporters.append(test_logger.TextTestLogger(options))

    for plugin in plugin_modules:
        if hasattr(plugin, "build_test_reporters"):
            reporters += plugin.build_test_reporters(options)

    test_runner_args = {
        'suites_include': options.suites_include,
        'suites_exclude': options.suites_exclude,
        'suites_require': options.suites_require,
        'failure_limit' : options.failure_limit,
        'module_method_overrides': module_method_overrides,
        'test_reporters': reporters,            # Should be pushed into plugin
        'options': options,
        'plugin_modules': plugin_modules
    }

    return runner_action, test_path, test_runner_args, options

def _parse_test_runner_command_line_module_method_overrides(args):
    """Parse a set of positional args (returned from an OptionParser probably) for specific modules or test methods.
    eg/ > python some_module_test.py SomeTestClass.some_test_method
    """

    test_path = args[0]

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
        command_line_args = command_line_args or sys.argv[1:]

        plugin_modules = load_plugins()

        runner_action, test_path, test_runner_args, other_opts = parse_test_runner_command_line_args(plugin_modules, command_line_args)

        self.setup_logging(other_opts)

        bucket_overrides = {}
        if other_opts.bucket_overrides_file:
            bucket_overrides = get_bucket_overrides(other_opts.bucket_overrides_file)

        if other_opts.serve_port:
            from test_runner_server import TestRunnerServer
            test_runner_class = TestRunnerServer
            test_runner_args['serve_port'] = other_opts.serve_port
        elif other_opts.connect_addr:
            from test_runner_client import TestRunnerClient
            test_runner_class = TestRunnerClient
            test_runner_args['connect_addr'] = other_opts.connect_addr
            test_runner_args['runner_id'] = other_opts.runner_id
        elif other_opts.replay_json or other_opts.replay_json_inline:
            from test_runner_json_replay import TestRunnerJSONReplay
            test_runner_class = TestRunnerJSONReplay
            test_runner_args['replay_json'] = other_opts.replay_json
            test_runner_args['replay_json_inline'] = other_opts.replay_json_inline
        else:
            test_runner_class = TestRunner

        runner = test_runner_class(
            test_path,
            bucket_overrides=bucket_overrides,
            bucket_count=other_opts.bucket_count,
            bucket_salt=other_opts.bucket_salt,
            bucket=other_opts.bucket,
            **test_runner_args
        )

        if runner_action == ACTION_LIST_SUITES:
            runner.list_suites()
            sys.exit(0)
        elif runner_action == ACTION_LIST_TESTS:
            runner.list_tests()
            sys.exit(0)
        elif runner_action == ACTION_RUN_TESTS:
            label_text = ""
            bucket_text = ""
            if other_opts.label:
                label_text = " " + other_opts.label
            if other_opts.bucket_count:
                salt_info =  (' [salt: %s]' % other_opts.bucket_salt) if other_opts.bucket_salt else ''
                bucket_text = " (bucket %d of %d%s)" % (other_opts.bucket, other_opts.bucket_count, salt_info)
            log.info("starting test run%s%s", label_text, bucket_text)
            result = runner.run()
            sys.exit(not result)

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


if __name__ == "__main__":
    TestProgram()
