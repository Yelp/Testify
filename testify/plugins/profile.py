import cProfile

def add_command_line_options(parser):
    parser.add_option("-p", "--profile", action="store_true", dest="profile")

def run_test_case(options, test_case, runnable):
    if options.profile:
        cprofile_filename = test_case.__class__.__module__ + "." + test_case.__class__.__name__ + '.cprofile'
        return cProfile.runctx('runnable()', globals(), locals(), cprofile_filename)
    else:
        return runnable()
    