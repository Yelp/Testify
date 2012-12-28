import contextlib
import os
import socket
import tempfile

catbox = None
try:
    import catbox
except ImportError:
    pass

import mock

import testify as T

from testify.plugins.violation_collector import ctx

from testify.plugins.violation_collector import cleandict
from testify.plugins.violation_collector import collect
from testify.plugins.violation_collector import is_sqlite_filepath
from testify.plugins.violation_collector import run_in_catbox
from testify.plugins.violation_collector import sqlite_dbpath
from testify.plugins.violation_collector import writeln

from testify.plugins.violation_collector import ViolationCollector
from testify.plugins.violation_collector import ViolationReporter
from testify.plugins.violation_collector import ViolationStore

@contextlib.contextmanager
def mocked_ctx(verbosity=None):
    with mock.patch('testify.plugins.violation_collector.ctx') as mock_ctx:
        yield mock_ctx


@contextlib.contextmanager
def mocked_store():
    with mock.patch('testify.plugins.violation_collector.SA'):
        mock_options = mock.Mock()
        mock_options.violation_dburl = "fake db url"
        mock_options.build_info = None

        ViolationStore.metadata = mock.Mock()
        ViolationStore.Violations = mock.Mock()
        ViolationStore.Tests = mock.Mock()
        yield ViolationStore(mock_options)


@contextlib.contextmanager
def sqlite_store():
    test_violations_file = "test_violations.sqlite"
    mock_options = mock.Mock()
    mock_options.violation_dburl = "sqlite:///%s" % test_violations_file
    mock_options.build_info = None

    yield ViolationStore(mock_options)
    os.unlink(test_violations_file)


@contextlib.contextmanager
def mocked_collector():
    collector = ViolationCollector()
    collector.store = mock.Mock()
    collector.violations_read_fd = mock.Mock()
    collector.violations_write_fd = mock.Mock()
    collector.epoll = mock.Mock()
    yield collector


class HelperFunctionsTestCase(T.TestCase):
    def test_is_sqliteurl(self):
        assert is_sqlite_filepath("sqlite:///")
        assert is_sqlite_filepath("sqlite:///test.db")
        assert is_sqlite_filepath("sqlite:////tmp/test-database.sqlite")

    def test_sqlite_dbpath(self):
        T.assert_equal(sqlite_dbpath("sqlite:///test.sqlite"), os.path.abspath("test.sqlite"))
        T.assert_equal(sqlite_dbpath("sqlite:////var/tmp/test.sqlite"), "/var/tmp/test.sqlite")

    def test_cleandict(self):
        dirty_dict = {'a': 1, 'b': 2, 'c': 3}
        clean_dict = {'a': 1}
        T.assert_equal(cleandict(dirty_dict, allowed_keys=['a']), clean_dict)

    def test_collect(self):
        with mock.patch('testify.plugins.violation_collector.ctx') as mock_ctx:
            mock_ctx.collector.get_violator.return_value = "fake_class1,fake_method1,tests.fake_module1"

            collect("fake_violation1", "", "")

            assert mock_ctx.collector.report_violation.called

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
            mctx.output_verbosity = T.test_logger.VERBOSITY_SILENT
            msg = "test message"

            writeln(msg)

            mctx.output_stream.write.assert_called_with(msg + "\n")
            assert mctx.output_stream.flush.called

    def test_writeln_with_verbosity_verbose(self):
        with mocked_ctx() as mctx:
            verbosity = T.test_logger.VERBOSITY_VERBOSE
            msg = "test message"
            mctx.output_verbosity = verbosity

            writeln(msg, verbosity)

            mctx.output_stream.write.assert_called_with(msg + "\n")
            assert mctx.output_stream.flush.called


class ViolationReporterTestCase(T.TestCase):

    @T.setup
    def setup_reporter(self):
        self.mock_result = mock.MagicMock()
        result_attrs = {
            'method' : 'mock_method',
            'class'  : 'mock_class',
            'name'   : 'mock_name',
            'module' : 'mock_module',
        }
        self.mock_result.configure_mocks(**result_attrs)
        self.mock_store = mock.Mock()
        self.mock_collector = mock.Mock()
        self.mock_collector.store = self.mock_store
        self.reporter = ViolationReporter(violation_collector=self.mock_collector)

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
        assert self.mock_collector.store.add_test.called

    def test_test_start(self):
        self.reporter.test_start(self.mock_result)
        assert self.mock_collector.store.add_test.called

    def test_class_setup_start(self):
        self.reporter.class_setup_start(self.mock_result)
        assert self.mock_collector.store.add_test.called

    def test_class_teardown_start(self):
        self.reporter.class_teardown_start(self.mock_result)
        assert self.mock_collector.store.add_test.called

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

class ViolationStoreTestCase(T.TestCase):

    def test_connect(self):
        with mocked_store() as mock_store:
            assert mock_store.engine.connect.called
            assert mock_store.metadata.create_all.called

    def test_add_test(self):
        with mocked_store() as mock_store:
            fake_test = mock.Mock()
            mock_store.add_test(fake_test)

            fake_test.update.assert_called_with(mock_store.info)
            assert mock_store.conn.execute.called
            assert mock_store.Tests.insert.called

    def test_add_violation(self):
        with mocked_store() as store:
            fake_test_id = 1
            fake_violation = mock.Mock()
            store.get_last_test_id = mock.Mock()
            store.get_last_test_id.return_value = fake_test_id

            store.add_violation(fake_violation)

            call_to_violation_update = fake_violation.update.call_args[0]
            first_arg_to_violation_update = call_to_violation_update[0]
            T.assert_equal(first_arg_to_violation_update, {'test_id': fake_test_id})
            assert store.conn.execute.called
            assert store.Violations.insert.called


class ViolationCollectorTestCase(T.TestCase):

    @T.class_setup
    def setup_fake_violator(self):
        self.fake_violator = "fake_class,fake_method,fake_module"

    def test_report_violation(self):
        with mocked_collector() as collector:
            fake_violator = ('fake_test_case', 'fake_method', 'fake_module')
            fake_violation = ('fake_syscall', 'fake_path')
            collector.report_violation(fake_violator, fake_violation)
            assert collector.store.add_violation.called


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
            raise Exception, msg + msg_pcre

        with sqlite_store() as store:
            collector = ViolationCollector()
            collector.store = store

            ctx.collector = collector

            reporter = ViolationReporter(violation_collector=collector)

            # Runing the test case inside catbox, we'll catch
            # violating syscalls and catbox will call our logger
            # function (collect)
            runner = T.test_runner.TestRunner(test_case, test_reporters=[reporter])
            run_in_catbox(runner.run, collect, [])

            yield store.violation_counts()

            ctx.collector = None

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
