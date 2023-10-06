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
from __future__ import print_function
from __future__ import absolute_import
from collections import defaultdict
from optparse import OptionParser
import os
import pprint
import sys
import logging
from importlib.machinery import SourceFileLoader

import testify
from testify import exit
from testify import test_logger
from testify.test_runner import TestRunner

ACTION_RUN_TESTS = 0
ACTION_LIST_SUITES = 1
ACTION_LIST_TESTS = 2

DEFAULT_PLUGIN_PATH = os.path.join(os.path.split(__file__)[0], 'plugins')

log = logging.getLogger('testify')


def load_plugins():
    """Load any plugin modules

    We load plugin modules based on directories provided to us by the environment, as well as a default in our own folder.

    Returns a list of module objects
    """
    # This function is a little wacky, doesn't seem like we SHOULD have to do all this just to get the behavior we want.
    # The idea will be to check out the directory contents and pick up any files that seem to match what python knows how to
    # import.

    plugin_directories = [DEFAULT_PLUGIN_PATH]
    if 'TESTIFY_PLUGIN_PATH' in os.environ:
        plugin_directories += os.environ['TESTIFY_PLUGIN_PATH'].split(':')

    plugin_modules = []
    for plugin_path in plugin_directories:
        for file_name in os.listdir(plugin_path):

            # For any file that we know how to load, try to import it
            if file_name.endswith('.py') and not file_name.startswith('.'):
                full_file_path = os.path.join(plugin_path, file_name)
                mod_name, suffix = os.path.splitext(file_name)
                # Need some unlikely-to-clash unique-ish module name
                mod_name = '_testify_plugin__' + mod_name

                try:
                    module_type = SourceFileLoader(mod_name, full_file_path).load_module()
                    plugin_modules.append(module_type)
                except TypeError:
                    continue
                except ImportError as e:
                    print("Failed to import plugin %s: %r" % (full_file_path, e), file=sys.stderr)
    return plugin_modules


def default_parser():
    """create the top-level parser, before adding plugins"""
    parser = OptionParser(
        usage="%prog <test path> [options]",
        version="%%prog %s" % testify.__version__,
        prog='testify')

    parser.set_defaults(verbosity=test_logger.VERBOSITY_NORMAL)
    parser.add_option("-s", "--silent", action="store_const", const=test_logger.VERBOSITY_SILENT, dest="verbosity")
    parser.add_option(
        "-v", "--verbose",
        action="store_const",
        const=test_logger.VERBOSITY_VERBOSE,
        dest="verbosity",
        help="Outputs a more verbose output and sets the root logger level to debug."
    )
    parser.add_option(
        '-d', '--ipdb', '--pdb',
        action="store_true",
        dest="debugger",
        help="Enter post mortem debugging mode with ipdb in the case of an exception thrown in a test method or fixture method.",
    )

    parser.add_option("-x", "--exclude-suite", action="append", dest="suites_exclude", type="string", default=[])
    parser.add_option("-q", "--require-suite", action="append", dest="suites_require", type="string", default=[])

    parser.add_option("--list-suites", action="store_true", dest="list_suites")
    parser.add_option("--list-tests", action="store_true", dest="list_tests")
    parser.add_option(
        '-f', "--list-tests-format", action="store", default="txt",
        help='controls the format of --list-tests',
    )

    parser.add_option("--label", action="store", dest="label", type="string", help="label for this test run")

    parser.add_option("--summary", action="store_true", dest="summary_mode")
    parser.add_option("--no-color", action="store_true", dest="disable_color", default=bool(not os.isatty(sys.stdout.fileno())))

    parser.add_option("--log-file", action="store", dest="log_file", type="string", default=None)
    parser.add_option("--log-level", action="store", dest="log_level", type="string", default="INFO")
    parser.add_option(
        '--print-log',
        action="append",
        dest="print_loggers",
        type="string",
        default=[],
        help="Direct logging output for these loggers to the console",
    )

    parser.add_option(
        '--failure-limit',
        '--maxfail',
        action="store",
        dest="failure_limit",
        type="int",
        default=None,
        help="Quit after this many test failures.",
    )

    parser.add_option(
        '--replay-json',
        action="store",
        dest="replay_json",
        type="string",
        default=None,
        help=(
            "Instead of discovering and running tests, read a file with one "
            "JSON-encoded test result dictionary per line, and report each "
            "line to test reporters as if we had just run that test."
        ),
    )
    parser.add_option(
        '--replay-json-inline',
        action="append",
        dest="replay_json_inline",
        type="string",
        metavar="JSON_OBJECT",
        help=(
            "Similar to --replay-json, but allows result objects to be passed "
            "on the command line. May be passed multiple times. If combined "
            "with --replay-json, inline results get reported first."
        ),
    )

    parser.add_option(
        '--rerun-test-file',
        action="store",
        metavar='FILE',
        dest="rerun_test_file",
        type="string",
        default=None,
        help=(
            "Rerun tests listed in FILE in order. One test per line, in the "
            "format 'path.to.class ClassName.test_method_name'. Consecutive "
            "tests in the same class will be run on the same test class "
            "instance."
        ),
    )

    return parser


def parse_test_runner_command_line_args(plugin_modules, args):
    """Parse command line args for the TestRunner to determine verbosity and other stuff"""
    parser = default_parser()

    # Add in any additional options
    for plugin in plugin_modules:
        if hasattr(plugin, 'add_command_line_options'):
            plugin.add_command_line_options(parser)

    (options, args) = parser.parse_args(args)
    if (
            len(args) < 1 and
            not (
                options.rerun_test_file or
                options.replay_json or
                options.replay_json_inline
            )
    ):
        parser.error(
            'Test path required unless --rerun-test-file, --replay-json, or '
            '--replay-json-inline specified.'
        )

    test_path, module_method_overrides = _parse_test_runner_command_line_module_method_overrides(args)

    if options.list_suites:
        runner_action = ACTION_LIST_SUITES
    elif options.list_tests:
        runner_action = ACTION_LIST_TESTS
    else:
        runner_action = ACTION_RUN_TESTS

    test_runner_args = {
        'debugger': options.debugger,
        'suites_exclude': options.suites_exclude,
        'suites_require': options.suites_require,
        'failure_limit': options.failure_limit,
        'module_method_overrides': module_method_overrides,
        'options': options,
        'plugin_modules': plugin_modules
    }

    return runner_action, test_path, test_runner_args, options


def _parse_test_runner_command_line_module_method_overrides(args):
    """Parse a set of positional args (returned from an OptionParser probably)
    for specific modules or test methods.
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
        """Run testify, return 0 on success, nonzero on failure."""
        self.setup_logging(self.other_opts)

        if self.other_opts.replay_json or self.other_opts.replay_json_inline:
            from .test_runner_json_replay import TestRunnerJSONReplay
            test_runner_class = TestRunnerJSONReplay
            self.test_runner_args['replay_json'] = self.other_opts.replay_json
            self.test_runner_args['replay_json_inline'] = self.other_opts.replay_json_inline
        elif self.other_opts.rerun_test_file:
            from .test_rerunner import TestRerunner
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
            **self.test_runner_args
        )

        if self.runner_action == ACTION_LIST_SUITES:
            suite_counts = runner.list_suites()
            pp = pprint.PrettyPrinter(indent=2)
            print(pp.pformat(dict(suite_counts)))
            return exit.OK
        elif self.runner_action == ACTION_LIST_TESTS:
            runner.list_tests(format=self.other_opts.list_tests_format)
            return exit.OK
        elif self.runner_action == ACTION_RUN_TESTS:
            label_text = ""
            if self.other_opts.label:
                label_text = " " + self.other_opts.label
            log.info("starting test run%s", label_text)

            # Allow plugins to modify the test runner.
            for plugin_mod in self.test_runner_args['plugin_modules']:
                if hasattr(plugin_mod, "prepare_test_runner"):
                    plugin_mod.prepare_test_runner(self.test_runner_args['options'], runner)

            return runner.run()

    def setup_logging(self, options):
        root_logger = logging.getLogger()
        if options.verbosity == test_logger.VERBOSITY_VERBOSE:
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


def run():
    """Entry point for running a test file directly."""
    args = ["__main__"] + sys.argv[1:]
    sys.exit(TestProgram(command_line_args=args).run())


def main():
    sys.exit(TestProgram().run())


if __name__ == "__main__":
    main()
