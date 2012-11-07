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
from testify import test_logger


VIOLATOR_DESC_END = "#END#"
MAX_VIOLATOR_LINE = 1024 * 10

verbosity = test_logger.VERBOSITY_NORMAL
violation_stream = None
violations = defaultdict(list)
last_violator = ("UndefinedTestCase", "UndefinedMethod", "UndefinedPath")

violations_read_fd, violations_write_fd = os.pipe()
epoll = select.epoll()
epoll.register(violations_read_fd, select.EPOLLIN | select.EPOLLET)

def writeln(msg):
    global violation_stream, verbosity
    if violation_stream and verbosity != test_logger.VERBOSITY_SILENT:
        msg = msg.encode('utf8') if isinstance(msg, unicode) else msg + '\n'
        violation_stream.write(msg)
        violation_stream.flush()

def report_violation(violator, violation):
    test_case, method, module = violator
    syscall, resolved_path = violation
    writeln("CATBOX_VIOLATION: %s.%s %r" % (test_case, method, violation))

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
        report_violation(violator, violation)
    except Exception, e:
		# No way to recover in here, just report error and violation
        writeln("Error collecting violation data. Error %r. Violation: %r" % (e, (operation, resolved_path)))


class ViolationReporter(test_reporter.TestReporter):
    def __init__(self, options, stream=sys.stdout):
        global violation_stream, violations_write_fd, verbosity
        self.options = options
        self.violations_write_fd = violations_write_fd
        if stream:
            violation_stream = stream
        verbosity = options.verbosity
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

    def report(self):
        global violations
        writeln("VIOLATION REPORT")
        for key, value in violations.iteritems():
			writeln(key + ":" + value)
        

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
