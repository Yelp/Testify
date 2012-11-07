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


class ViolationCollector:
    VIOLATOR_DESC_END = "#END#"
    MAX_VIOLATOR_LINE = 1024

    stream = None
    verbosity = test_logger.VERBOSITY_NORMAL
    violations = defaultdict(list)
    last_violator = ("UndefinedTestCase", "UndefinedMethod", "UndefinedPath")

    violations_read_fd, violations_write_fd = os.pipe()
    epoll = select.epoll()
    epoll.register(violations_read_fd, select.EPOLLIN | select.EPOLLET)

    def writeln(self, msg):
        if self.stream and self.verbosity != test_logger.VERBOSITY_SILENT:
            msg = msg.encode('utf8') if isinstance(msg, unicode) else msg + '\n'
            self.stream.write(msg)
            self.stream.flush()

    def report_violation(self, violator, violation):
        test_case, method, module = violator
        syscall, resolved_path = violation
        self.writeln("CATBOX_VIOLATION: %s.%s %r" % (test_case, method, violation))

    def get_violator(self):
        events = self.epoll.poll(.01)
        violator_line = ""
        if events:
            read = os.read(events[0][0], self.MAX_VIOLATOR_LINE)
            if read:
                # get last non empty string as violator line
                violator_line = read.split(self.VIOLATOR_DESC_END)[-2]
                self.last_violator = tuple(violator_line.split(','))
        return self.last_violator

collector = ViolationCollector()

def collect(operation, path, resolved_path):
    """This is the 'logger' method passed to catbox. This method
    will be triggered at each catbox violation.
    """
    global collector
    try:
        violator = collector.get_violator()
        violation = (operation, resolved_path)
        collector.violations[violator].append(violation)
        collector.report_violation(violator, violation)
    except Exception, e:
		# No way to recover in here, just report error and violation
        collector.writeln("Error collecting violation data. Error %r. Violation: %r" % (e, (operation, resolved_path)))


class ViolationReporter(test_reporter.TestReporter):
    def __init__(self, options, stream=sys.stdout):
        global collector
        self.collector = collector
        self.options = options
        self.violations_write_fd = self.collector.violations_write_fd
        if stream:
            self.collector.stream = stream
        self.collector.verbosity = options.verbosity
        super(ViolationReporter, self).__init__(self)

    def set_violator(self, test_case_name, method_name, module_path):
        violator_line = ','.join([test_case_name, method_name, module_path])
        os.write(self.violations_write_fd, violator_line + self.collector.VIOLATOR_DESC_END)

    def __update_violator(self, result):
        method = result['method']
        test_case_name = method['class']
        test_method_name = method['name']
        module_path = method['module']
        self.set_violator(test_case_name, test_method_name, module_path)

    def test_case_start(self, result):
        self.__update_violator(result)

    def test_case_complete(self, result):
        self.collector.get_violator()

    def test_start(self, result):
        self.__update_violator(result)

    def test_complete(self, result):
        self.collector.get_violator()

    def test_setup_start(self, result):
        self.__update_violator(result)

    def test_setup_complete(self, result):
        self.collector.get_violator()

    def test_teardown_start(self, result):
        self.__update_violator(result)

    def test_teardown_complete(self, result):
        self.collector.get_violator()

    def report(self):
        # TODO: fetch violations from DB and report here
        pass
        

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
