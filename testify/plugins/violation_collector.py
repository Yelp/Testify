from collections import defaultdict
import logging
import os
import Queue
import select
import sys
import threading
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
    SA.Column('module', SA.String(255), nullable=False),
    SA.Column('class_name', SA.String(255), nullable=False),
    SA.Column('method_name', SA.String(255), nullable=False),
    SA.Column('syscall', SA.String(20), index=True, nullable=False),
    SA.Column('syscall_args', SA.String(255), nullable=True),
    SA.Column('start_time', SA.Integer, index=True, nullable=False),
)
SA.Index('ix_individual_test', Violations.c.module, Violations.c.class_name, Violations.c.method_name, unique=False)
SA.Index('ix_syscall_signature', Violations.c.syscall, Violations.c.syscall_args, unique=False)

def is_sqliteurl(dburl):
    return dburl.startswith("sqlite:///")

def sqlite_dbpath(dburl):
    if is_sqliteurl(dburl):
        return os.path.abspath(dburl[len("sqlite:///"):])
    return None

class ViolationStore:
    def __init__(self, options):
        self.options = options
        self.dburl = self.options.violation_dburl or SA.engine.url.URL(**yaml.safe_load(open(self.options.violation_dbconfig)))
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
        metadata.create_all(engine)
        return engine, conn

    def start_daemon(self):
        self.violation_queue = Queue.Queue()
        self.db_thread = threading.Thread(target=self.flush_queue)
        self.db_thread.daemon = True
        self.db_thread.start()

    def add_violation(self, violation):
        self.violation_queue.put(violation)

    def flush_queue(self, daemon=True):
        if daemon:
            engine, conn = self.connect()
        else:
            engine, conn = self.engine, self.conn
        while True:
            violations = []
            if daemon:
                violations.append(self.violation_queue.get())
            try:
                while True:
                    violations.append(self.violation_queue.get_nowait())
            except Queue.Empty:
                pass
            try:
                if violations:
                    conn.execute(Violations.insert(), violations)
            except Exception, e:
                logging.error("Exception inserting violations: %r" % e)
            finally:
                for _ in xrange(len(violations)):
                    self.violation_queue.task_done()
            if not daemon:
                return

    def violation_counts_by_syscall(self):
        self.flush_queue(daemon=False)

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

    def writeln(self, msg):
        if self.stream and self.verbosity != test_logger.VERBOSITY_SILENT:
            msg = msg.encode('utf8') if isinstance(msg, unicode) else msg
            self.stream.write(msg + '\n')
            self.stream.flush()

    def report_violation(self, violator, violation):
        test_case, method, module = violator
        syscall, resolved_path = violation
        self.writeln("CATBOX_VIOLATION: %s.%s %r" % (test_case, method, violation))
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
(collection syscall violations) and one in the child running TestCases
(and reporing active module/test case class/test method."""
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
        self.collector.store.start_daemon()
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
        # TODO: do we need to use collector to write?
        self.collector.writeln("")
        self.collector.writeln("=" * 72)
        self.collector.writeln("VIOLATIONS (syscall, count):")
        for syscall, count in violations:
            self.collector.writeln("%s\t%s" % (syscall, count))

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
        default="sqlite:///test_violations.sqlite",
        help="URL of the SQL database to store violations."
    )
    parser.add_option(
        "--violation-db-config",
        dest="violation_dbconfig",
        help="Yaml configuration file describing SQL database to store violations."
    )

def build_test_reporters(options):
    if options.catbox_violations:
        return [ViolationReporter(options)]
    return []


def prepare_test_runner(options, runner):
    if options.catbox_violations:
        def _run():
            return run_in_catbox(runner.__original_run__, options)
        runner.__original_run__ = runner.run
        runner.run = _run
