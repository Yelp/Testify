from collections import defaultdict
import os
import select
import sys

catbox = None
try:
    import catbox
except ImportError:
    pass

from testify import test_reporter


VIOLATOR_DESC_END = "#END#"
MAX_VIOLATOR_LINE = 1024 * 10

violation_logger = None
violations = defaultdict(list)
violations_read_fd, violations_write_fd = os.pipe()
epoll = select.epoll()
epoll.register(violations_read_fd, select.EPOLLIN | select.EPOLLET)

last_violator = ("UndefinedTestCase", "UndefinedMethod", "UndefinedPath")

def _log(msg):
    global violation_logger
    if violation_logger:
        violation_logger.warning(msg)
    else:
        sys.stderr.write(msg + '\n')

def get_violator():
    global last_violator
    events = epoll.poll(.01)
    violator_line = ""
    if events:
        read = os.read(events[0][0], MAX_VIOLATOR_LINE)
        if read:
            # get last non empty string as violator line
            violator_line = read.split(VIOLATOR_DESC_END)[-2]
            last_violator = tuple(violator_line.split(','))
    return last_violator

def collect(operation, path, resolved_path):
    """This is the 'logger' method passed to catbox. This method
    will be triggered at each catbox violation.
    """
    global violations, last_violator
    try:
        violator = get_violator()
        violation = (operation, resolved_path)
        violations[violator].append(violation)
        test_case, method, _ = violator
        _log("CATBOX_VIOLATION: %s.%s %r" % (test_case, method, violation))
    except Exception, e:
		# No way to recover in here, just report error and violation
        _log("Error collecting violation data: %r" % e)
        _log("CATBOX_VIOLATION: " + str((operation, resolved_path)))


class ViolationReporter(test_reporter.TestReporter):
    def __init__(self, options, logger=None):
        global violation_logger, violations_write_fd
        self.options = options
        self.violations_write_fd = violations_write_fd
        if logger:
            violation_logger = logger
        super(ViolationReporter, self).__init__(self)

    def set_violator(self, test_case_name, method_name, module_path):
        violator_line = ','.join([test_case_name, method_name, module_path])
        os.write(self.violations_write_fd, violator_line + VIOLATOR_DESC_END)

    def __update_violator(self, result):
        global set_violator
        method = result['method']
        test_case_name = method['class']
        test_method_name = method['name']
        module_path = method['module']
        self.set_violator(test_case_name, test_method_name, module_path)

    def test_case_start(self, result):
        self.__update_violator(result)

    def test_start(self, result):
        self.__update_violator(result)

    def test_setup_start(self, result):
        self.__update_violator(result)

    def test_teardown_start(self, result):
        self.__update_violator(result)

def run_in_catbox(method):
    if not catbox:
        return method()

    return catbox.run(
        method,
        collect_only=True,
        network=False,
        logger=collect,
        writable_paths=["~.*pyc$", "~.*\/logs\/app.log$", "/dev/null"]
    ).code


def add_command_line_options(parser):
    parser.add_option(
        "-V",
        "--collect-violations",
        action="store_true",
        dest="catbox_violations",
        help="Network or filesystem access from tests will be reported as violations."
    )


def build_test_reporters(options):
    if options.catbox_violations:
        return [ViolationReporter(options)]
    return []


def prepare_test_runner(options, runner):
    if options.catbox_violations:
        def _run():
            return run_in_catbox(runner.__original_run__)
        runner.__original_run__ = runner.run
        runner.run = _run
