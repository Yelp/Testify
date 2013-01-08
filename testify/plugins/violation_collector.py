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
    store = None
    output_stream = None
    output_verbosity = test_logger.VERBOSITY_NORMAL

'''Catbox will fork this process and run TestProgram in the child. The
child process runs the tests while the parent process traces the
tests' execution.

The instances created by this module in this global context will have
two copies: one in parent (collecting syscall violations) and one in
the traced child process (running tests).'''
ctx = _Context()


def is_sqlite_filepath(dburl):
    '''Check if dburl is an sqlite file path.'''
    return dburl.startswith('sqlite:///')


def sqlite_dbpath(dburl):
    '''Return the file path of the sqlite url'''
    if is_sqlite_filepath(dburl):
        return os.path.abspath(dburl[len('sqlite:///'):])
    return None


def cleandict(dictionary, allowed_keys):
    '''Cleanup the dictionary removing all keys but the allowed ones.'''
    return dict((k, v) for k, v in dictionary.iteritems() if k in allowed_keys)


def writable_paths(options):
    '''Generate a list of writable paths'''
    paths = ['~.*pyc$', '/dev/null']
    if is_sqlite_filepath(options.violation_dburl):
        paths.append('~%s.*$' % sqlite_dbpath(options.violation_dburl))
    return paths


def run_in_catbox(method, logger, paths):
    '''Run the given method in catbox. method is going to be run in
    catbox to be traced and logger will be notified of any violations
    in the method.

    paths is a list of writable strings (regexp). Catbox will ignore
    violations by syscalls if the syscall is call writing to a path in
    the writable paths list.
    '''
    if not catbox: return method()

    return catbox.run(
        method,
        collect_only=True,
        network=False,
        logger=logger,
        writable_paths=paths,
    ).code


def writeln(msg, verbosity=None):
    '''Write msg to the output stream appending a new line'''
    global ctx
    verbosity =  verbosity or ctx.output_verbosity
    if ctx.output_stream and (verbosity <= ctx.output_verbosity):
        msg = msg.encode('utf8') if isinstance(msg, unicode) else msg
        ctx.output_stream.write(msg + '\n')
        ctx.output_stream.flush()


def collect(syscall, path, resolved_path):
    '''This is the 'logger' method passed to catbox. This method
    will be triggered at each catbox violation.
    '''
    global ctx
    try:
        writeln(
            'CATBOX_VIOLATION: %s, %s' % (syscall, resolved_path),
            test_logger.VERBOSITY_VERBOSE
        )

        ctx.store.add_violation({
            'syscall': syscall,
            'syscall_args': resolved_path,
            'start_time': time.time()
        })
    except Exception, e:
        # No way to recover in here, just report error and violation
        sys.stderr.write('Error collecting violation data. Error %r. Violation: %r\n' % (e, (syscall, resolved_path)))


class ViolationStore(object):
    metadata = SA.MetaData()
    
    Violations = SA.Table(
        'catbox_violations', metadata,
        SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
        SA.Column('test_id', SA.Integer, index=True, nullable=False),
        SA.Column('syscall', SA.String(20), nullable=False),
        SA.Column('syscall_args', SA.Text, nullable=True),
        SA.Column('start_time', SA.Integer),
    )
    
    Tests = SA.Table(
        'catbox_tests', metadata,
        SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
        SA.Column('branch', SA.Text),
        SA.Column('revision', SA.Text),
        SA.Column('submitstamp', SA.Integer),
        SA.Column('start_time', SA.Integer),
        SA.Column('module', SA.Text, nullable=False),
        SA.Column('class_name', SA.Text, nullable=False),
        SA.Column('method_name', SA.Text, nullable=False),
    )

    TEST_ID_DESC_END = '#'
    MAX_TEST_ID_LINE = 1024 * 10

    def __init__(self, options):
        self.options = options
        self.dburl = self.options.violation_dburl or SA.engine.url.URL(**yaml.safe_load(open(self.options.violation_dbconfig)))
        if options.build_info:
            info = json.loads(options.build_info)
            self.info = cleandict(info, ['branch', 'revision', 'submitstamp'])
        else:
            self.info = {'branch': '', 'revision': '', 'submitstamp': time.time()}

        if is_sqlite_filepath(self.dburl):
            if self.dburl.find(':memory:') > -1:
                raise ValueError('Can not use sqlite memory database for ViolationStore')
            dbpath = sqlite_dbpath(self.dburl)
            if os.path.exists(dbpath):
                os.unlink(dbpath)

        self.last_test_id = 0
        self._setup_pipe()

        self.engine, self.conn = self._connect_db()

    def _setup_pipe(self):
        """Setup a pipe to enable communication between parent and
        traced child processes.

        Adding tests and adding violations to the database is done
        through different processes. We use this pipe to update the
        last test id to be used while inserting Violations. Although
        it is possible to get it from the database we'll use the pipe
        not to make a db query each time we add a violation (and would
        really work when there is multiple builders writing to the
        database).
        """
        self.test_id_read_fd, self.test_id_write_fd = os.pipe()
        self.epoll = select.epoll()
        self.epoll.register(self.test_id_read_fd, select.EPOLLIN | select.EPOLLET)

    def _connect_db(self):
        engine = SA.create_engine(self.dburl)
        conn = engine.connect()
        if is_sqlite_filepath(self.dburl):
            conn.execute('PRAGMA journal_mode = MEMORY;')
        self.metadata.create_all(engine)
        return engine, conn

    def _set_last_test_id(self, test_id):
        """Set the latest test id inserted to the database. See the
        _setup_pipe's docstring for details.
        """
        if self.test_id_read_fd:
            # If this method is called it means that we're in the
            # traced child process. Reporter (running in the traced
            # child process) will ultimately call this method to write
            # the test id to the pipe when we start running a test
            # method. Closing the read end of the pipe as we don't
            # need to read/write from there.
            os.close(self.test_id_read_fd)
            self.test_id_read_fd = None

        os.write(self.test_id_write_fd, '%d%s' % (test_id, self.TEST_ID_DESC_END))

    def _parse_last_test_id(self, data):
        """Get last non empty string as violator line."""
        test_id_str = data.split(self.TEST_ID_DESC_END)[-2]
        return int(test_id_str)

    def get_last_test_id(self):
        """Get the latest test id inserted to the database. See the
        setup_pipe's docstring for details.
        """
        if self.test_id_write_fd:
            # If this method is called it means that we're in the
            # parent process. Parent process will use this method to
            # read from pipe and learn about the running test method
            # to report violations. Closing the write end of the pipe
            # as we don't need to read/write from there.
            os.close(self.test_id_write_fd)
            self.test_id_write_fd = None

        events = self.epoll.poll(.01)
        if events:
            read = os.read(events[0][0], self.MAX_TEST_ID_LINE)
            if read:
                self.last_test_id = self._parse_last_test_id(read)
        return self.last_test_id

    def add_test(self, module, class_name, method_name):
        try:
            testinfo = {
                'module': module,
                'class_name': class_name,
                'method_name': method_name,
                'start_time': time.time(),
            }
            testinfo.update(self.info)
            result = self.conn.execute(self.Tests.insert(), testinfo)
            self._set_last_test_id(result.lastrowid)
        except Exception, e:
            logging.error('Exception inserting testinfo: %r' % e)

    def add_violation(self, violation):
        try:
            test_id = self.get_last_test_id()
            violation.update({'test_id': test_id})
            self.conn.execute(self.Violations.insert(), violation)
        except Exception, e:
            logging.error('Exception inserting violations: %r' % e)

    def violation_counts(self):
        query = SA.sql.select([
            self.Tests.c.class_name,
            self.Tests.c.method_name,
            self.Violations.c.syscall,
            SA.sql.func.count(self.Violations.c.syscall).label('count')

        ]).where(
            self.Violations.c.test_id == self.Tests.c.id
        ).group_by(
            self.Tests.c.class_name, self.Tests.c.method_name, self.Violations.c.syscall
        ).order_by(
            'count DESC'
        )
        result = self.conn.execute(query)
        violations = []
        for row in result:
            violations.append((row['class_name'], row['method_name'], row['syscall'], row['count']))
        return violations


class ViolationReporter(test_reporter.TestReporter):
    def __init__(self, options, store):
        self.options = options
        self.store = store
        super(ViolationReporter, self).__init__(self)

    def __update_violator(self, result):
        method = result['method']
        test_case_name = method['class']
        test_method_name = method['name']
        module_path = method['module']
        self.store.add_test(module_path, test_case_name, test_method_name)

    def test_case_start(self, result):
        self.__update_violator(result)

    def test_start(self, result):
        self.__update_violator(result)

    def class_setup_start(self, result):
        self.__update_violator(result)

    def class_teardown_start(self, result):
        self.__update_violator(result)

    def get_syscall_count(self, violations):
        syscall_violations = []
        for syscall, violators in itertools.groupby(sorted(violations, key=operator.itemgetter(2)), operator.itemgetter(2)):
            count = sum(violator[3] for violator in violators)
            syscall_violations.append((syscall, count))
        return sorted(syscall_violations, key=operator.itemgetter(1))

    def get_violations_count(self, syscall_violation_counts):
        return sum(count for (syscall, count) in syscall_violation_counts)

    def report(self):
        violations = self.store.violation_counts()
        if ctx.output_verbosity == test_logger.VERBOSITY_VERBOSE:
            self._report_verbose(violations)
        elif ctx.output_verbosity >= test_logger.VERBOSITY_NORMAL:
            self._report_normal(violations)
        else:
            self._report_silent(violations)

    def _report_verbose(self, violations):
        verbosity = test_logger.VERBOSITY_VERBOSE
        self._report_normal(violations)
        writeln('')
        for class_name, test_method, syscall, count in violations:
            writeln('%s.%s\t%s\t%s' % (class_name, test_method, syscall, count), verbosity)

    def _report_normal(self, violations):
        if not len(violations):
            writeln('No syscall violations! \o/\n', test_logger.VERBOSITY_NORMAL)
            return
        self._report_silent(violations)

    def _report_silent(self, violations):
        syscall_violation_counts = self.get_syscall_count(violations)
        violations_count = self.get_violations_count(syscall_violation_counts)
        violations_line = '%s %s' % (
            '%s syscall violations:' % violations_count,
            ','.join(['%s (%s)' % (syscall, count) for syscall, count in syscall_violation_counts])
        )
        writeln(violations_line, test_logger.VERBOSITY_SILENT)



def add_command_line_options(parser):
    parser.add_option(
        '-V',
        '--collect-violations',
        action='store_true',
        dest='catbox_violations',
        help='Network or filesystem access from tests will be reported as violations.'
    )
    parser.add_option(
        '--violation-db-url',
        dest='violation_dburl',
        default='sqlite:///violations.sqlite',
        help='URL of the SQL database to store violations.'
    )
    parser.add_option(
        '--violation-db-config',
        dest='violation_dbconfig',
        help='Yaml configuration file describing SQL database to store violations.'
    )


def prepare_test_program(options, program):
    global ctx
    if options.catbox_violations:
        ctx.output_stream = sys.stderr # TODO: Use logger?
        ctx.output_verbosity = options.verbosity
        ctx.store = ViolationStore(options)
        def _run():
            return run_in_catbox(
                program.__original_run__,
                collect,
                writable_paths(options)
            )
        program.__original_run__ = program.run
        program.run = _run


def build_test_reporters(options):
    global ctx
    if options.catbox_violations:
        msg_pcre = '\nhttps://github.com/Yelp/catbox/wiki/Install-Catbox-with-PCRE-enabled\n'
        if not catbox:
            msg = 'Violation collection requires catbox and you do not have it installed in your PYTHONPATH.\n'
            msg += msg_pcre
            raise Exception, msg
        if catbox and not catbox.has_pcre():
            msg = 'Violation collection requires catbox compiled with PCRE. Your catbox installation does not have PCRE support.'
            msg += msg_pcre
            raise Exception, msg
        return [ViolationReporter(options, ctx.store)]
    return []
