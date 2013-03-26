import fcntl
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

SA = None
try:
    import sqlalchemy as SA
except ImportError:
    pass
import yaml

from testify import test_reporter
from testify import test_logger


method_types = ('undefined', 'test', 'setup', 'teardown', 'class_setup', 'class_teardown')

(
    UNDEFINED_METHOD_TYPE,
    TEST_METHOD_TYPE,
    SETUP_METHOD_TYPE,
    TEARDOWN_METHOD_TYPE,
    CLASS_SETUP_METHOD_TYPE,
    CLASS_TEARDOWN_METHOD_TYPE
) = method_types


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

def get_db_url(options):
    '''If a configuration file is given, returns the database URL from
    the configuration file. Otherwise returns violation-db-url option.
    '''
    if options.violation_dbconfig:
        with open(options.violation_dbconfig) as db_config_file:
            return SA.engine.url.URL(**yaml.safe_load(db_config_file))
    else:
        return options.violation_dburl

def is_sqlite_filepath(dburl):
    '''Check if dburl is an sqlite file path.'''
    return type(dburl) in (str, unicode) and dburl.startswith('sqlite:///')


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
    TEST_ID_DESC_END = ','
    MAX_TEST_ID_LINE = 1024 * 10

    def __init__(self, options):
        self.options = options

        self.dburl = get_db_url(self.options)
        if options.build_info:
            info = json.loads(options.build_info)
            self.info = cleandict(info, ['branch', 'revision', 'buildbot_run_id'])
        else:
            self.info = {'branch': '', 'revision': '', 'buildbot_run_id': None}

        self.init_database()

        if is_sqlite_filepath(self.dburl):
            if self.dburl.find(':memory:') > -1:
                raise ValueError('Can not use sqlite memory database for ViolationStore')
            dbpath = sqlite_dbpath(self.dburl)
            if os.path.exists(dbpath):
                os.unlink(dbpath)

        self.last_test_id = 0
        self._setup_pipe()

        self.engine = self.conn = None

    def init_database(self):
        self.metadata = SA.MetaData()

        self.Violations = SA.Table(
            'catbox_violations', self.metadata,
            SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
            SA.Column('test_id', SA.Integer, index=True, nullable=False),
            SA.Column('syscall', SA.String(20), nullable=False),
            SA.Column('syscall_args', SA.Text, nullable=True),
            SA.Column('start_time', SA.Integer),
        )

        self.Methods = SA.Table(
            'catbox_methods', self.metadata,
            SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
            SA.Column('buildbot_run_id', SA.String(36), index=True, nullable=True),
            SA.Column('branch', SA.Text),
            SA.Column('revision', SA.Text),
            SA.Column('start_time', SA.Integer),
            SA.Column('module', SA.Text, nullable=False),
            SA.Column('class_name', SA.Text, nullable=False),
            SA.Column('method_name', SA.Text, nullable=False),
            SA.Column('method_type', SA.Enum(*method_types), nullable=False),
        )

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

        fcntl.fcntl(self.test_id_read_fd, fcntl.F_SETFL, os.O_NONBLOCK)
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
        for fileno, event in events:
            if event == select.EPOLLIN:
                read = os.read(fileno, self.MAX_TEST_ID_LINE)
                if read:
                    self.last_test_id = self._parse_last_test_id(read)
        return self.last_test_id

    def add_method(self, module, class_name, method_name, method_type):
        if self.engine is None and self.conn is None:
            # We are in the traced child process and this is the first
            # request to add a test to the database. We should create
            # a connection for this process. Note that making the
            # connection earlier would not work as the connection
            # object would be shared by two processes and cause
            # deadlock in mysql client library.
            self.engine, self.conn = self._connect_db()
        try:
            testinfo = {
                'module': module,
                'class_name': class_name,
                'method_name': method_name,
                'start_time': time.time(),
                'method_type': method_type,
            }
            testinfo.update(self.info)
            result = self.conn.execute(self.Methods.insert(), testinfo)
            self._set_last_test_id(result.lastrowid)
        except Exception, e:
            logging.error('Exception inserting testinfo: %r' % e)

    def add_violation(self, violation):
        if self.engine is None and self.conn is None:
            # We are in the parent process and this is the first
            # request to add a violation to the database. We should
            # create a connection for this process.
            #
            # As in add_method (see above), making the connection
            # earlier would not work due due to deadlock issues.
            self.engine, self.conn = self._connect_db()
        try:
            test_id = self.get_last_test_id()
            violation.update({'test_id': test_id})
            self.conn.execute(self.Violations.insert(), violation)
        except Exception, e:
            logging.error('Exception inserting violations: %r' % e)

    def violation_counts(self):
        query = SA.sql.select([
            self.Methods.c.class_name,
            self.Methods.c.method_name,
            self.Violations.c.syscall,
            SA.sql.func.count(self.Violations.c.syscall).label('count')

        ]).where(
            self.Violations.c.test_id == self.Methods.c.id
        ).group_by(
            self.Methods.c.class_name, self.Methods.c.method_name, self.Violations.c.syscall
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
        super(ViolationReporter, self).__init__(options)

    def __update_violator(self, result, method_type):
        method = result['method']
        test_case_name = method['class']
        test_method_name = method['name']
        module_path = method['module']
        self.store.add_method(module_path, test_case_name, test_method_name, method_type)

    def test_case_start(self, result):
        self.__update_violator(result, UNDEFINED_METHOD_TYPE)

    def test_start(self, result):
        self.__update_violator(result, TEST_METHOD_TYPE)

    def class_setup_start(self, result):
        self.__update_violator(result, CLASS_SETUP_METHOD_TYPE)

    def class_teardown_start(self, result):
        self.__update_violator(result, CLASS_TEARDOWN_METHOD_TYPE)

    def get_syscall_count(self, violations):
        syscall_violations = []
        for syscall, violators in itertools.groupby(sorted(violations, key=operator.itemgetter(2)), operator.itemgetter(2)):
            count = sum(violator[3] for violator in violators)
            syscall_violations.append((syscall, count))
        return sorted(syscall_violations, key=operator.itemgetter(1))

    def get_violations_count(self, syscall_violation_counts):
        return sum(count for (syscall, count) in syscall_violation_counts)

    def report(self):
        if self.options.disable_violations_summary is not True:
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
    parser.add_option(
        '--disable-violations-summary',
        action='store_true',
        dest='disable_violations_summary',
        help='Disable preparing a summary .'
    )


def prepare_test_program(options, program):
    global ctx
    if options.catbox_violations:
        if not sys.platform.startswith('linux'):
            msg = 'Violation collection plugin is Linux-specific. Please either run your tests on Linux or disable the plugin.'
            raise Exception, msg
        msg_pcre = '\nhttps://github.com/Yelp/catbox/wiki/Install-Catbox-with-PCRE-enabled\n'
        if not catbox:
            msg = 'Violation collection requires catbox and you do not have it installed in your PYTHONPATH.\n'
            msg += msg_pcre
            raise ImportError, msg
        if catbox and not catbox.has_pcre():
            msg = 'Violation collection requires catbox compiled with PCRE. Your catbox installation does not have PCRE support.'
            msg += msg_pcre
            raise ImportError, msg
        if not SA:
            msg = 'Violation collection requires sqlalchemy and you do not have it installed in your PYTHONPATH.\n'
            raise ImportError, msg

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
        return [ViolationReporter(options, ctx.store)]
    return []
