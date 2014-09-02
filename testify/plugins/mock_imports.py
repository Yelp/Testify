import imp

def add_command_line_options(parser):
    parser.add_option(
        '--mock-importing-module',
        dest='mock_importing_module',
        default=None,
        help='Name of the module that will import and install testing mocks prior to test discovery.'
    )

def _import_rec(mods, parent=None):
    if len(mods) == 0:
        return parent
    mod = mods[0]
    if parent is None:
        pathname = None
    else:
        pathname = parent.__path__
    return _import_rec(mods[1:], imp.load_module(mod, *imp.find_module(mod, pathname)))

def prepare_test_program(options, program):
    name = options.mock_importing_module
    if name:
        try:
            _import_rec(name.split('.'))
        except ImportError:
            raise

