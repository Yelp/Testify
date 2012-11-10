from collections import defaultdict
import json
import logging
import os
import select
import sys
import time

catbox = None
try:
    import catbox
except ImportError:
    pass
import sqlalchemy as SA
import yaml

from testify import test_reporter
from testify import test_logger


metadata = SA.MetaData()

Violations = SA.Table(
    'violations', metadata,
    SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
    SA.Column('branch', SA.String(255)),
    SA.Column('revision', SA.String(255)),
    SA.Column('submitstamp', SA.Integer),
    SA.Column('module', SA.String(255), nullable=False),
    SA.Column('class_name', SA.String(255), nullable=False),
    SA.Column('method_name', SA.String(255), nullable=False),
    SA.Column('syscall', SA.String(20), index=True, nullable=False),
    SA.Column('syscall_args', SA.String(255), nullable=True),
)
SA.Index('ix_unique_build', Violations.c.branch, Violations.c.revision, Violations.c.submitstamp)
SA.Index('ix_individual_test', Violations.c.module, Violations.c.class_name, Violations.c.method_name)
SA.Index('ix_syscall_signature', Violations.c.syscall, Violations.c.syscall_args)

def is_sqliteurl(dburl):
    return dburl.startswith("sqlite:///")

def sqlite_dbpath(dburl):
    if is_sqliteurl(dburl):
        return os.path.abspath(dburl[len("sqlite:///"):])
    return None

def cleandict(dictionary, allowed_keys):
    new_dict = {}
    for key in dictionary.iterkeys():
        new_dict[key] = dictionary[key]
    return new_dict

class ViolationStore:
    def __init__(self, options):
        self.options = options
        self.dburl = self.options.violation_dburl or SA.engine.url.URL(**yaml.safe_load(open(self.options.violation_dbconfig)))
        if options.build_info:
            info = json.loads(options.build_info)
            self.info = cleandict(info, ['branch', 'revision', 'submitstamp'])
        else:
            self.info = {'branch': "", 'revision': "", 'submitstamp': time.time()}

        if is_sqliteurl(self.dburl):
            if self.dburl.find(":memory:") > -1:
                raise ValueError("Can not use sqlite memory database for ViolationStore")
            dbpath = sqlite_dbpath(self.dburl)
            if os.path.exists(dbpath):
                os.unlink(dbpath)

        self.engine, self.conn = self.connect()

    def connect(self):
        engine = SA.create_engine(self.dburl)
        conn = engine.connect()
        if is_sqliteurl(self.dburl):
            conn.execute("PRAGMA journal_mode = MEMORY;")
        metadata.create_all(engine)
        return engine, conn

    def add_violation(self, violation):
        try:
            violation.update(self.info)
            self.conn.execute(Violations.insert(), violation)
        except Exception, e:
            logging.error("Exception inserting violations: %r" % e)
        finally:
            self.violation_queue = []

    def violation_counts_by_syscall(self):
        query = SA.sql.select([
            Violations.c.syscall,
            SA.sql.func.count(Violations.c.syscall).label("count")
        ]).group_by(Violations.c.syscall).order_by("count DESC")
        result = self.conn.execute(query)
        violations = []
        for row in result:
            violations.append((row['syscall'], row['count']))
        return violations


class ViolationCollector:
    VIOLATOR_DESC_END = "#END#"
    MAX_VIOLATOR_LINE = 1024

    store = None
    stream = None
    verbosity = test_logger.VERBOSITY_NORMAL
    violations = defaultdict(list)
    last_violator = ("UndefinedTestCase", "UndefinedMethod", "UndefinedPath")

    violations_read_fd, violations_write_fd = os.pipe()
    epoll = select.epoll()
    epoll.register(violations_read_fd, select.EPOLLIN | select.EPOLLET)

    def writeln(self, msg, verbosity=None):
        if not verbosity:
            verbosity = self.verbosity
        if self.stream and verbosity <= self.verbosity:
            msg = msg.encode('utf8') if isinstance(msg, unicode) else msg
            self.stream.write(msg + '\n')
            self.stream.flush()

    def report_violation(self, violator, violation):
        test_case, method, module = violator
        syscall, resolved_path = violation
        self.writeln(
            "CATBOX_VIOLATION: %s.%s %r" % (test_case, method, violation),
            test_logger.VERBOSITY_VERBOSE
        )
        self.store.add_violation({
                "module": module,
                "class_name": test_case,
                "method_name": method,
                "syscall": syscall,
                "syscall_args": resolved_path,
                "start_time": time.time()
        })

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


"""We'll have two copies of this collector instance, one in parent
(collecting syscall violations) and one in the child running TestCases
(and reporting active module/test_case/test_method."""
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
        self.collector.store = ViolationStore(options)
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
        violations = self.collector.store.violation_counts_by_syscall()
        verbosity = test_logger.VERBOSITY_SILENT
        self.collector.writeln("", verbosity)
        self.collector.writeln("=" * 72, verbosity)
        self.collector.writeln("VIOLATIONS (syscall, count):", verbosity)
        for syscall, count in violations:
            self.collector.writeln("%s\t%s" % (syscall, count), verbosity)

def run_in_catbox(method, options):
    if not catbox:
        return method()

    paths = ["~.*pyc$", "~.*\/logs\/app.log$", "/dev/null"]
    if is_sqliteurl(options.violation_dburl):
        paths.append("~%s.*$" % sqlite_dbpath(options.violation_dburl))

    return catbox.run(
        method,
        collect_only=True,
        network=False,
        logger=collect,
        writable_paths=paths
    ).code


def add_command_line_options(parser):
    parser.add_option(
        "-V",
        "--collect-violations",
        action="store_true",
        dest="catbox_violations",
        help="Network or filesystem access from tests will be reported as violations."
    )
    parser.add_option(
        "--violation-db-url",
        dest="violation_dburl",
        default="sqlite:///violations.sqlite",
        help="URL of the SQL database to store violations."
    )
    parser.add_option(
        "--violation-db-config",
        dest="violation_dbconfig",
        help="Yaml configuration file describing SQL database to store violations."
    )

def build_test_reporters(options):
    if options.catbox_violations:
        if not catbox:
            raise Exception, "Violation collection requires catbox. You do not have catbox install in your path."
        if not catbox.has_pcre():
            raise Exception, "Violation collection requires catbox compiled with PCRE. Your catbox installation does not have PCRE support."
        return [ViolationReporter(options)]
    return []


def prepare_test_runner(options, runner):
    if options.catbox_violations:
        def _run():
            return run_in_catbox(runner.__original_run__, options)
        runner.__original_run__ = runner.run
        runner.run = _run
