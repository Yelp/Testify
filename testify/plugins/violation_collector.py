from collections import defaultdict
import itertools
import json
import logging
import operator
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


class _Context(object):
    collector = None
    output_stream = None
    output_verbosity = test_logger.VERBOSITY_NORMAL

"""Catbox run will fork the process and run the our TestProgram in the
child. Although test methods will be running in the child catbox will
do the tracing in the parent process.

The instances created by this module, as this global context instance,
will have two copies. One in parent (collecting syscall violations)
and one in the traced child process (running tests)."""
ctx = _Context()


def is_sqlite_filepath(dburl):
    """Check if dburl is an sqlite file path."""
    return dburl.startswith("sqlite:///")


def sqlite_dbpath(dburl):
    """Return the file path of the sqlite url"""
    if is_sqlite_filepath(dburl):
        return os.path.abspath(dburl[len("sqlite:///"):])
    return None


def cleandict(dictionary, allowed_keys):
    """Cleanup the dictionary removing all keys but the allowed ones."""
    return dict((k, v) for k, v in dictionary.iteritems() if k in allowed_keys)


def writeable_paths(options):
    """Generate a list of writeable paths"""
    paths = ["~.*pyc$", "/dev/null"]
    if is_sqlite_filepath(options.violation_dburl):
        paths.append("~%s.*$" % sqlite_dbpath(options.violation_dburl))
    return paths


def run_in_catbox(method, logger, paths):
    """Run the given method in catbox. method is going to be run in
    catbox to be traced and logger will be notified of any violations
    in the method.

    paths is a list of writable strings (regexp). Catbox will ignore
    violations by syscalls if the syscall is call writing to a path in
    the writable paths list.
    """
    if not catbox: return method()

    return catbox.run(
        method,
        collect_only=True,
        network=False,
        logger=logger,
        writable_paths=paths,
    ).code


def writeln(msg, verbosity=None):
    """Write msg to the output stream appending a new line"""
    global ctx
    verbosity =  verbosity or ctx.output_verbosity
    if ctx.output_stream and (verbosity <= ctx.output_verbosity):
        msg = msg.encode('utf8') if isinstance(msg, unicode) else msg
        ctx.output_stream.write(msg + '\n')
        ctx.output_stream.flush()


def collect(operation, path, resolved_path):
    """This is the 'logger' method passed to catbox. This method
    will be triggered at each catbox violation.
    """
    global ctx
    try:
        violator = ctx.collector.get_violator()
        violation = (operation, resolved_path)
        ctx.collector.violations[violator].append(violation)
        ctx.collector.report_violation(violator, violation)
    except Exception, e:
        # No way to recover in here, just report error and violation
        sys.stderr.write("Error collecting violation data. Error %r. Violation: %r" % (e, (operation, resolved_path)))


class ViolationStore:
    metadata = SA.MetaData()
    
    Violations = SA.Table(
        'catbox_violations', metadata,
        SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
        SA.Column('test_id', SA.Integer, nullable=False),
        SA.Column('syscall', SA.String(20), index=True, nullable=False),
        SA.Column('syscall_args', SA.String(255), nullable=True),
        SA.Column('start_time', SA.Integer),
    )
    SA.Index('ix_syscall_signature', Violations.c.syscall, Violations.c.syscall_args)
    SA.Index('ix_violating_test_id', Violations.c.test_id)
    
    Tests = SA.Table(
        'catbox_tests', metadata,
        SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
        SA.Column('branch', SA.String(255)),
        SA.Column('revision', SA.String(255)),
        SA.Column('submitstamp', SA.Integer),
        SA.Column('module', SA.String(255), nullable=False),
        SA.Column('class_name', SA.String(255), nullable=False),
        SA.Column('method_name', SA.String(255), nullable=False),
    )
    SA.Index('ix_build', Tests.c.branch, Tests.c.revision, Tests.c.submitstamp)
    SA.Index('ix_individual_test', Tests.c.module, Tests.c.class_name, Tests.c.method_name)

    # Adding tests and adding violations to the database is done
    # through different processes. We use this pipe to update the last
    # test id to be used while inserting Violations. Although it is
    # possible to get it from the database we'll use the pipe not to
    # make a db query each time we add a violation.
    test_id_read_fd, test_id_write_fd = os.pipe()
    epoll = select.epoll()
    epoll.register(test_id_read_fd, select.EPOLLIN | select.EPOLLET)

    TEST_ID_DESC_END = "#END#"
    MAX_TEST_ID_LINE = 1024

    last_test_id = 0

    def __init__(self, options):
        self.options = options
        self.dburl = self.options.violation_dburl or SA.engine.url.URL(**yaml.safe_load(open(self.options.violation_dbconfig)))
        if options.build_info:
            info = json.loads(options.build_info)
            self.info = cleandict(info, ['branch', 'revision', 'submitstamp'])
        else:
            self.info = {'branch': "", 'revision': "", 'submitstamp': time.time()}

        if is_sqlite_filepath(self.dburl):
            if self.dburl.find(":memory:") > -1:
                raise ValueError("Can not use sqlite memory database for ViolationStore")
            dbpath = sqlite_dbpath(self.dburl)
            if os.path.exists(dbpath):
                os.unlink(dbpath)

        self.engine, self.conn = self.connect()

    def connect(self):
        engine = SA.create_engine(self.dburl)
        conn = engine.connect()
        if is_sqlite_filepath(self.dburl):
            conn.execute("PRAGMA journal_mode = MEMORY;")
        self.metadata.create_all(engine)
        return engine, conn

    def add_test(self, testinfo):
        try:
            testinfo.update(self.info)
            result = self.conn.execute(self.Tests.insert(), testinfo)
            # update the test id for add_violation to use it to insert
            # violations for a method
            test_id = result.lastrowid
            self.set_last_test_id(test_id)
        except Exception, e:
            logging.error("Exception inserting testinfo: %r" % e)

    def add_violation(self, violation):
        try:
            test_id = self.get_last_test_id()
            violation.update({'test_id': test_id})
            self.conn.execute(self.Violations.insert(), violation)
        except Exception, e:
            logging.error("Exception inserting violations: %r" % e)

    def violation_counts(self):
        query = SA.sql.select([
            self.Tests.c.class_name,
            self.Tests.c.method_name,
            self.Violations.c.syscall,
            SA.sql.func.count(self.Violations.c.syscall).label("count")
        ]).where(
			self.Violations.c.test_id == self.Tests.c.id
		).group_by(
			self.Tests.c.class_name, self.Tests.c.method_name, self.Violations.c.syscall
		).order_by(
			"count DESC"
		)
        result = self.conn.execute(query)
        violations = []
        for row in result:
            violations.append((row['class_name'], row['method_name'], row['syscall'], row['count']))
        return violations

    def _get_last_test_id(self, data):
        # get last non empty string as violator line
        test_id_str = data.split(self.TEST_ID_DESC_END)[-2]
        return int(test_id_str)

    def get_last_test_id(self):
        events = self.epoll.poll(.01)
        if events:
            read = os.read(events[0][0], self.MAX_TEST_ID_LINE)
            if read:
                self.last_test_id = self._get_last_test_id(read)
        return self.last_test_id

    def set_last_test_id(self, test_id):
        os.write(self.test_id_write_fd, "%d%s" % (test_id, self.TEST_ID_DESC_END))


class ViolationCollector:
    VIOLATOR_DESC_END = "#END#"
    MAX_VIOLATOR_LINE = 1024

    store = None
    stream = None
    violations = defaultdict(list)

    UNDEFINED_VIOLATOR = ("UndefinedTestCase", "UndefinedMethod", "UndefinedPath")
    last_violator = UNDEFINED_VIOLATOR

    # Simmilar to the mechanism in ViolationStore (read the comment in
    # ViolationStore), ViolationCollector will get the violating test
    # method information from ViolationReporter, which runs on a
    # different process, by reading this pipe.
    violations_read_fd, violations_write_fd = os.pipe()
    epoll = select.epoll()
    epoll.register(violations_read_fd, select.EPOLLIN | select.EPOLLET)

    def report_violation(self, violator, violation):
        if violator == self.UNDEFINED_VIOLATOR:
            # This is coming from Testify, not from a TestCase. Ignoring.
            return

        test_case, method, module = violator
        syscall, resolved_path = violation
        writeln(
            "CATBOX_VIOLATION: %s.%s %r" % (test_case, method, violation),
            test_logger.VERBOSITY_VERBOSE
        )
        self.store.add_violation({
                "syscall": syscall,
                "syscall_args": resolved_path,
                "start_time": time.time()
        })

    def _get_last_violator(self, data):
        # get last non empty string as violator line
        violator_line = data.split(self.VIOLATOR_DESC_END)[-2]
        return tuple(violator_line.split(','))

    def get_violator(self):
        events = self.epoll.poll(.01)
        if events:
            read = os.read(events[0][0], self.MAX_VIOLATOR_LINE)
            if read:
                self.last_violator = self._get_last_violator(read)
        return self.last_violator


class ViolationReporter(test_reporter.TestReporter):
    def __init__(self, violation_collector=None):
        global ctx
        self.collector = violation_collector or ctx.collector
        self.violations_write_fd = self.collector.violations_write_fd
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
        self.collector.store.add_test({
                'method_name' : test_method_name,
                'class_name' : test_case_name,
                'module' : module_path
        })
                

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

    def get_syscall_count(self, violations):
        syscall_violations = []
        for syscall, violators in itertools.groupby(sorted(violations, key=operator.itemgetter(2)), operator.itemgetter(2)):
            count = sum(violator[3] for violator in violators)
            syscall_violations.append((syscall, count))
        return sorted(syscall_violations, key=operator.itemgetter(1))

    def report(self):
        violations = self.collector.store.violation_counts()
        if ctx.output_verbosity == test_logger.VERBOSITY_VERBOSE:
            self._report_verbose(violations)
        elif ctx.output_verbosity >= test_logger.VERBOSITY_NORMAL:
            self._report_normal(violations)
        else:
            self._report_silent(violations)

    def _report_verbose(self, violations):
        verbosity = test_logger.VERBOSITY_VERBOSE
        self._report_normal(violations)
        writeln("")
        for class_name, test_method, syscall, count in violations:
            writeln("%s.%s\t%s\t%s" % (class_name, test_method, syscall, count), verbosity)

    def _report_normal(self, violations):
        if not len(violations):
            writeln("No syscall violations! \o/\n", test_logger.VERBOSITY_NORMAL)
            return
        self._report_silent(violations)

    def _report_silent(self, violations):
        syscall_violations = ['%s (%s)' % counts for counts in self.get_syscall_count(violations)]
        violations_line = "%s %s" % (
            "%s syscall violations:" % len(violations),
            ','.join(syscall_violations)
        )
        writeln(violations_line, test_logger.VERBOSITY_SILENT)



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
        return [ViolationReporter()]
    return []


def prepare_test_program(options, program):
    global ctx
    if options.catbox_violations:
        ctx.output_stream = sys.stderr # TODO: Use logger?
        ctx.output_verbosity = options.verbosity

        ctx.collector = ViolationCollector()
        ctx.collector.store = ViolationStore(options)
        def _run():
            return run_in_catbox(
                program.__original_run__,
                collect,
                writeable_paths(options)
            )
        program.__original_run__ = program.run
        program.run = _run
