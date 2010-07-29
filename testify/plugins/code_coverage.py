from testify.utils import code_coverage

def add_command_line_options(parser):
    parser.add_option("-c", "--coverage", action="store_true", dest="coverage")

def run_test_case(options, test_case, runnable):
    if options.coverage:
        code_coverage.start(test_case.__class__.__module__ + "." + test_case.__class__.__name__)
        return runnable()
        code_coverage.stop()
    else:
        return runnable()
