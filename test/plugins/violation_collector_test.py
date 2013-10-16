import contextlib
import os
import socket
import tempfile
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

import mock

import testify as T

from testify.plugins.violation_collector import ctx

from testify.plugins.violation_collector import cleandict
from testify.plugins.violation_collector import collect
from testify.plugins.violation_collector import get_db_url
from testify.plugins.violation_collector import is_sqlite_filepath
from testify.plugins.violation_collector import run_in_catbox
from testify.plugins.violation_collector import sqlite_dbpath
from testify.plugins.violation_collector import writeln

from testify.plugins.violation_collector import ViolationReporter
from testify.plugins.violation_collector import ViolationStore

from testify.plugins.violation_collector import TEST_METHOD_TYPE


@contextlib.contextmanager
def mocked_ctx():
    with mock.patch('testify.plugins.violation_collector.ctx') as mock_ctx:
        yield mock_ctx


@contextlib.contextmanager
def mocked_store():
    def mock_init_database(obj):
        obj.metadata = mock.MagicMock()
        obj.Violations = mock.MagicMock()
        obj.Methods = mock.MagicMock()

    with mock.patch('testify.plugins.violation_collector.SA'):
        mock_options = mock.Mock()
        mock_options.violation_dburl = "fake db url"
        mock_options.violation_dbconfig = None
        mock_options.build_info = None

        # we're doing our own method paching here because
        # mock.patch.object's side_effect functions are not passed in
        # the object.
        original_init_database = ViolationStore.init_database
        ViolationStore.init_database = mock_init_database
        yield ViolationStore(mock_options)
        ViolationStore.init_database = original_init_database


@contextlib.contextmanager
def sqlite_store():
    test_violations_file = "test_violations.sqlite"
    mock_options = mock.Mock()
    mock_options.violation_dburl = "sqlite:///%s" % test_violations_file
    mock_options.violation_dbconfig = None
    mock_options.build_info = None

    yield ViolationStore(mock_options)

    os.unlink(test_violations_file)


@contextlib.contextmanager
def mocked_reporter(store):
    mock_options = mock.Mock()
    reporter = ViolationReporter(mock_options, store)
    yield reporter


class HelperFunctionsTestCase(T.TestCase):
    def test_get_db_url_with_dburl(self):
        options = mock.Mock()
        options.violation_dburl = 'sqlite:///fake/database'
        options.violation_dbconfig = None
        T.assert_equal(get_db_url(options), options.violation_dburl)

    def test_get_db_url_with_dbconfig(self):
        options = mock.Mock()
        options.violation_dburl = 'sqlite:///fake/database'
        options.violation_dbconfig = '/fake/path/to/db/'

        mocked_open = mock.Mock(spec=file)
        mocked_open.__enter__ = mock.Mock()
        mocked_open.__exit__ = mock.Mock()
        with mock.patch(
            'testify.plugins.violation_collector.open',
            create=True,
            return_value=mocked_open
        ):
            with mock.patch.object(SA.engine.url, 'URL') as mocked_sa_url:
                T.assert_not_equal(get_db_url(options), options.violation_dburl)
                mocked_open.read.assert_called
                mocked_sa_url.URL.assert_called

    def test_is_sqliteurl(self):
        assert is_sqlite_filepath("sqlite:///")
        assert is_sqlite_filepath("sqlite:///test.db")
        assert is_sqlite_filepath("sqlite:////tmp/test-database.sqlite")

        sa_engine_url = SA.engine.url.URL(drivername='mysql', host='fakehost', database='fakedb')
        T.assert_equal(is_sqlite_filepath(sa_engine_url), False)

    def test_sqlite_dbpath(self):
        T.assert_equal(sqlite_dbpath("sqlite:///test.sqlite"), os.path.abspath("test.sqlite"))
        T.assert_equal(sqlite_dbpath("sqlite:////var/tmp/test.sqlite"), "/var/tmp/test.sqlite")

    def test_cleandict(self):
        dirty_dict = {'a': 1, 'b': 2, 'c': 3}
        clean_dict = {'a': 1}
        T.assert_equal(cleandict(dirty_dict, allowed_keys=['a']), clean_dict)

    def test_collect(self):
        with mocked_ctx() as mock_ctx:
            fake_time = 10
            with mock.patch.object(time, 'time', return_value=fake_time):
                fake_violation = "fake_violation1"
                fake_resolved_path = "fake_resolved_path"
                collect(fake_violation, "", fake_resolved_path)

                fake_violation_data = {
                    'syscall': fake_violation,
                    'syscall_args': fake_resolved_path,
                    'start_time': fake_time
                }
                mock_ctx.store.add_violation.assert_called_with(fake_violation_data)


    def test_run_in_catbox(self):
        with mock.patch('testify.plugins.violation_collector.catbox') as mock_catbox:
            mock_method = mock.Mock()
            mock_logger = mock.Mock()
            mock_paths = mock.Mock()

            run_in_catbox(mock_method, mock_logger, mock_paths)

            mock_catbox.run.assert_called_with(
                mock_method,
                collect_only=True,
                network=False,
                logger=mock_logger,
                writable_paths=mock_paths,
            )

    def test_writeln_with_default_verbosity(self):
        with mocked_ctx() as mctx:
            msg = "test message"

            writeln(msg)

            mctx.output_stream.write.assert_called_with(msg + "\n")
            assert mctx.output_stream.flush.called

    def test_writeln_with_verbosity_silent(self):
        with mocked_ctx() as mctx:
            # when ctx.output_verbosity is defined as silent and we
            # want to write a message in in VERBOSITY_SILENT, we
            # should still see the message.
            verbosity = T.test_logger.VERBOSITY_SILENT
            mctx.output_verbosity = T.test_logger.VERBOSITY_SILENT
            msg = "test message"

            writeln(msg, verbosity)

            mctx.output_stream.write.assert_called_with(msg + "\n")
            assert mctx.output_stream.flush.called

    def test_writeln_with_verbosity_verbose(self):
        with mocked_ctx() as mctx:
            # should see verbose messages in a verbose context.
            verbosity = T.test_logger.VERBOSITY_VERBOSE
            msg = "test message"
            mctx.output_verbosity = verbosity

            writeln(msg, verbosity)

            mctx.output_stream.write.assert_called_with(msg + "\n")
            assert mctx.output_stream.flush.called

    def test_writeln_with_verbosity_verbose_in_silent_context(self):
        with mocked_ctx() as mctx:
            # when the context is defined as silent, verbose level
            # messages should be ignored.
            mctx.output_verbosity = T.test_logger.VERBOSITY_SILENT
            msg = "test message"

            writeln(msg, T.test_logger.VERBOSITY_VERBOSE)

            T.assert_equal(mctx.output_stream.flush.called, False)


class ViolationReporterTestCase(T.TestCase):

    @T.setup_teardown
    def setup_reporter(self):
        self.mock_result = mock.MagicMock()
        result_attrs = {
            'method' : 'mock_method',
            'class'  : 'mock_class',
            'name'   : 'mock_name',
            'module' : 'mock_module',
        }
        self.mock_result.configure_mocks(**result_attrs)
        store = mock.Mock()
        with mocked_reporter(store) as reporter:
            self.mock_store = store
            reporter.options.disable_violations_summary = False
            self.reporter = reporter
            yield

    @T.setup
    def setup_fake_violations(self):
        self.fake_violations = [
            ('fake_class1', 'fake_method1', 'fake_violation1', 5),
            ('fake_class1', 'fake_method2', 'fake_violation2', 5),
            ('fake_class2', 'fake_method3', 'fake_violation3', 5),
            ('fake_class3', 'fake_method4', 'fake_violation1', 5),
        ]

    def test_test_case_start(self):
        self.reporter.test_case_start(self.mock_result)
        assert self.mock_store.add_method.called

    def test_test_start(self):
        self.reporter.test_start(self.mock_result)
        assert self.mock_store.add_method.called

    def test_class_setup_start(self):
        self.reporter.class_setup_start(self.mock_result)
        assert self.mock_store.add_method.called

    def test_class_teardown_start(self):
        self.reporter.class_teardown_start(self.mock_result)
        assert self.mock_store.add_method.called

    def test_get_syscall_count(self):
        T.assert_equal(
            self.reporter.get_syscall_count(self.fake_violations),
            [('fake_violation2', 5), ('fake_violation3', 5), ('fake_violation1', 10)]
        )

    def test_get_violations_count(self):
        syscall_violation_counts = self.reporter.get_syscall_count(self.fake_violations)
        T.assert_equal(
            self.reporter.get_violations_count(syscall_violation_counts),
            sum(count for violating_class, violating_method, violation, count in self.fake_violations)
        )

    def test_report_with_no_violations(self):
        with mock.patch('testify.plugins.violation_collector.writeln') as mock_writeln:
            self.mock_store.violation_counts.return_value = []

            self.reporter.report()

            mock_writeln.assert_called_with(
                "No syscall violations! \o/\n",
                T.test_logger.VERBOSITY_NORMAL
            )

    def test_report_with_violations(self):
        with mocked_ctx() as mctx:
            mctx.output_verbosity = T.test_logger.VERBOSITY_VERBOSE
            fake_violation = [
                ('fake_class1', 'fake_method1', 'fake_violation1', 5),
            ]
            self.mock_store.violation_counts.return_value = fake_violation

            self.reporter.report()
            mctx.output_stream.write.assert_called_with("%s.%s\t%s\t%s\n" % fake_violation[0])

    def test_report_with_violations_summary_disabled(self):
        with mocked_ctx() as mctx:
            # reporter is created in a setup method and safe to alter
            self.reporter.options.disable_violations_summary = True

            mctx.output_verbosity = T.test_logger.VERBOSITY_VERBOSE
            fake_violation = [
                ('fake_class1', 'fake_method1', 'fake_violation1', 5),
            ]
            self.mock_store.violation_counts.return_value = fake_violation

            self.reporter.report()
            T.assert_equal(mctx.output_stream.write.called, False)


@T.suite("catbox")
class ViolationStoreTestCase(T.TestCase):

    def test_violation_store_does_not_connect_db_when_initialized(self):
        with mocked_store() as mock_store:
            T.assert_equal(mock_store.engine, None)
            T.assert_equal(mock_store.conn, None)

    def test_add_method(self):
        with mocked_store() as mock_store:
            mock_store._set_last_test_id = mock.Mock()
            mock_store.add_method("fake_module", "fake_class", "fake_method", TEST_METHOD_TYPE)

            assert mock_store.engine.connect.called
            assert mock_store.conn.execute.called
            assert mock_store.Methods.insert.called

    def test_add_violation(self):
        with mocked_store() as mock_store:
            fake_test_id = 1
            fake_violation = mock.Mock()
            mock_store.get_last_test_id = mock.Mock()
            mock_store.get_last_test_id.return_value = fake_test_id

            mock_store.add_violation(fake_violation)

            call_to_violation_update = fake_violation.update.call_args[0]
            first_arg_to_violation_update = call_to_violation_update[0]
            T.assert_equal(first_arg_to_violation_update, {'test_id': fake_test_id})

            assert mock_store.engine.connect.called
            assert mock_store.conn.execute.called
            assert mock_store.Violations.insert.called


@T.suite("catbox")
class ViolationCollectorPipelineTestCase(T.TestCase):

    class ViolatingTestCase(T.TestCase):
        def make_filesystem_violation(self, suffix):
            fd, fpath = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            os.unlink(fpath)

        def make_network_violation(self):
            s = socket.socket()
            s.connect(("127.0.0.1", 80))
            s.close()

        def test_filesystem_violation(self):
            self.make_filesystem_violation("fake_testfile")

        def test_network_violation(self):
            self.make_network_violation()

    class ViolatingTestCaseWithSetupAndTeardown(ViolatingTestCase):

        @T.setup
        def __setup(self):
            self.make_filesystem_violation("fake_testcase_setup")

        @T.teardown
        def __teardown(self):
            self.make_filesystem_violation("fake_testcase_teardown")

    class ViolatingTestCaseWithClassSetupAndTeardown(ViolatingTestCase):

        @T.class_setup
        def __class_setup(self):
            self.make_filesystem_violation("fake_testcase_class_setup")

        @T.class_teardown
        def __class_teardown(self):
            self.make_filesystem_violation("fake_testcase_class_teardown")

    @contextlib.contextmanager
    def run_testcase_in_catbox(self, test_case):
        if not catbox:
            msg = 'Violation collection pipeline tests require catbox.\n'
            msg_pcre = 'https://github.com/Yelp/catbox/wiki/Install-Catbox-with-PCRE-enabled\n'
            raise ImportError, msg + msg_pcre

        with sqlite_store() as store:
            with mocked_reporter(store) as reporter:
                ctx.store = store

                # Runing the test case inside catbox, we'll catch
                # violating syscalls and catbox will call our logger
                # function (collect)
                runner = T.test_runner.TestRunner(test_case, test_reporters=[reporter])
                run_in_catbox(runner.run, collect, [])

                yield store.violation_counts()

                ctx.store = None

    def test_catbox_methods_inserts(self):
        with self.run_testcase_in_catbox(self.ViolatingTestCase):
            query = SA.sql.select([
                ctx.store.Methods.c.class_name,
                ctx.store.Methods.c.method_name,
                ctx.store.Methods.c.method_type,
            ]).where(
                SA.and_(
                    ctx.store.Methods.c.class_name == 'ViolatingTestCase',
                    ctx.store.Methods.c.method_name == 'test_filesystem_violation',
                    ctx.store.Methods.c.method_type == TEST_METHOD_TYPE,
                )
            )
            result = ctx.store.conn.execute(query).fetchone()
            T.assert_equal(result, ('ViolatingTestCase', 'test_filesystem_violation', TEST_METHOD_TYPE))

    def test_catbox_violations_inserts(self):
        with self.run_testcase_in_catbox(self.ViolatingTestCase):
            query = SA.sql.select([
                ctx.store.Violations.c.syscall,
            ]).where(
                ctx.store.Violations.c.syscall == 'socketcall',
            )
            result = ctx.store.conn.execute(query).fetchall()
            T.assert_equal(len(result), 1)

    def test_violation_collector_pipeline(self):
        with self.run_testcase_in_catbox(self.ViolatingTestCase) as violations:
            T.assert_in(
                (u'ViolatingTestCase', u'test_network_violation', u'socketcall', 1),
                violations
            )
            T.assert_in(
                (u'ViolatingTestCase', u'test_filesystem_violation', u'unlink', 2),
                violations
            )
            T.assert_in(
                (u'ViolatingTestCase', u'test_filesystem_violation', u'open', 2),
                violations
            )

    def test_violation_collector_pipeline_with_fixtures(self):
        with self.run_testcase_in_catbox(self.ViolatingTestCaseWithSetupAndTeardown) as violations:
            # setup/teardown fixtures will bump the unlink count for test_filesystem_violation by 2
            T.assert_in(
                (u'ViolatingTestCaseWithSetupAndTeardown', u'test_filesystem_violation', u'unlink', 4),
                violations
            )
            # setup/teardown fixtures will bump the open count for test_filesystem_violation by 2
            T.assert_in(
                (u'ViolatingTestCaseWithSetupAndTeardown', u'test_filesystem_violation', u'open', 4),
                violations
            )

    def test_violation_collector_pipeline_with_class_level_fixtures(self):
        with self.run_testcase_in_catbox(self.ViolatingTestCaseWithClassSetupAndTeardown) as violations:
            T.assert_in(
                (u'ViolatingTestCaseWithClassSetupAndTeardown', u'__class_setup', u'open', 2),
                violations
            )
            T.assert_in(
                (u'ViolatingTestCaseWithClassSetupAndTeardown', u'__class_setup', u'unlink', 2),
                violations
            )
            T.assert_in(
                (u'ViolatingTestCaseWithClassSetupAndTeardown', u'__class_teardown', u'open', 1),
                violations
            )
            T.assert_in(
                (u'ViolatingTestCaseWithClassSetupAndTeardown', u'__class_teardown', u'unlink', 1),
                violations
            )

if __name__ == '__main__':
    T.run()
