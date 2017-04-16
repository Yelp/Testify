# -*- coding: utf-8 -*-
import imp

def add_command_line_options(parser):
    parser.add_option(
        '--startup-module',
        nargs=1,
        help="specify a module to import before any of the tests are run."
    )


def prepare_test_program(options, _):
    if options.startup_module is None:
        return

    # we just need to pick a name that isn't likely to cause a conflict.
    imp.load_source('__startup.module', options.startup_module)
