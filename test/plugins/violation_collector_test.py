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
def mocked_writeln(verbosity=None):
    with mock.patch('testify.plugins.violation_collector.output_stream') as mock_stream:
        test_message = "test message"
        writeln(test_message, verbosity)
        yield test_message, mock_stream


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
        with mock.patch('testify.plugins.violation_collector.collector') as mock_collector:
            mock_collector.get_violator.return_value = "fake_class1,fake_method1,tests.fake_module1"

            collect("fake_violation1", "", "")

            assert mock_collector.get_violator.called
            assert mock_collector.report_violation.called

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
        with mocked_writeln() as data:
            msg, stream = data
            stream.write.assert_called_with(msg + "\n")
            assert stream.flush.called

    def test_writeln_with_verbosity_silent(self):
        with mocked_writeln(verbosity=T.test_logger.VERBOSITY_SILENT) as data:
            msg, stream = data
            stream.write.assert_called_with(msg + "\n")
            assert stream.flush.called

    def test_writeln_with_verbosity_verbose(self):
        with mocked_writeln(verbosity=T.test_logger.VERBOSITY_VERBOSE) as data:
            msg, stream = data
            T.assert_equal(stream.write.called, False)
            T.assert_equal(stream.flush.called, False)


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
        self.mock_set_violator = mock.Mock()
        self.reporter = ViolationReporter(violation_collector=self.mock_collector)
        self.reporter.set_violator = self.mock_set_violator

    def test_test_case_start(self):
        self.reporter.test_case_start(self.mock_result)
        assert self.mock_set_violator.called
        assert self.mock_collector.store.add_test.called

    def test_test_case_complete(self):
        self.reporter.test_case_complete(self.mock_result)
        assert self.mock_collector.get_violator.called

    def test_test_start(self):
        self.reporter.test_start(self.mock_result)
        assert self.mock_set_violator.called
        assert self.mock_collector.store.add_test.called

    def test_test_complete(self):
        self.reporter.test_complete(self.mock_result)
        assert self.mock_collector.get_violator.called

    def test_test_setup_start(self):
        self.reporter.test_setup_start(self.mock_result)
        assert self.mock_set_violator.called
        assert self.mock_collector.store.add_test.called

    def test_test_setup_complete(self):
        self.reporter.test_setup_complete(self.mock_result)
        assert self.mock_collector.get_violator.called

    def test_test_teardown_start(self):
        self.reporter.test_teardown_start(self.mock_result)
        assert self.mock_set_violator.called
        assert self.mock_collector.store.add_test.called

    def test_test_teardown_complete(self):
        self.reporter.test_teardown_complete(self.mock_result)
        assert self.mock_collector.get_violator.called

    def test_get_syscall_count(self):
        fake_violations = [
            ('fake_class1', 'fake_method1', 'fake_violation1', 5),
            ('fake_class1', 'fake_method2', 'fake_violation2', 5),
            ('fake_class2', 'fake_method3', 'fake_violation3', 5),
            ('fake_class3', 'fake_method4', 'fake_violation1', 5),
        ]
        T.assert_equal(
            self.reporter.get_syscall_count(fake_violations),
            [('fake_violation2', 5), ('fake_violation3', 5), ('fake_violation1', 10)]
        )

    def test_report_with_no_violations(self):
        with mock.patch('testify.plugins.violation_collector.writeln') as mock_writeln:
            self.mock_store.violation_counts.return_value = []

            self.reporter.report()

            mock_writeln.assert_called_with(
                "No unit test violations! \o/\n",
                T.test_logger.VERBOSITY_SILENT
            )

    def test_report_with_violations(self):
        with mock.patch('testify.plugins.violation_collector.writeln') as mock_writeln:
            fake_violation = [
                ('fake_class1', 'fake_method1', 'fake_violation1', 5),
            ]
            self.mock_store.violation_counts.return_value = fake_violation

            self.reporter.report()

            mock_writeln.assert_called_with(
                "%s.%s\t%s\t%s" % fake_violation[0],
                T.test_logger.VERBOSITY_SILENT
            )

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
        with mocked_store() as mock_store:
            fake_violation = mock.Mock()
            mock_store.add_violation(fake_violation)

            fake_violation.update.assert_called_with(mock_store.info)
            assert mock_store.conn.execute.called
            assert mock_store.Violations.insert.called


class ViolationCollectorTestCase(T.TestCase):

    @T.class_setup
    def setup_fake_violator(self):
        self.fake_violator = "fake_class,fake_method,fake_module"
        self.fake_violator_line =  self.fake_violator + ViolationCollector.VIOLATOR_DESC_END

    def test_report_violation(self):
        with mocked_collector() as collector:
            fake_violator = ('fake_test_case', 'fake_method', 'fake_module')
            fake_violation = ('fake_syscall', 'fake_path')
            collector.report_violation(fake_violator, fake_violation)
            assert collector.store.add_violation.called

    def test_get_last_violator(self):
        with mocked_collector() as collector:
            T.assert_equal(
                collector._get_last_violator(self.fake_violator_line),
                tuple(self.fake_violator.split(','))
            )

    def test_get_violator(self):
        with mocked_collector() as collector:
            collector.epoll.poll.return_value = [['fake_file_descriptor']]
            with mock.patch('testify.plugins.violation_collector.os') as mock_os:
                mock_os.read.return_value = self.fake_violator_line
                collector._get_last_violator = mock.Mock()

                collector.get_violator()
                
                mock_os.read.assert_called_with('fake_file_descriptor', collector.MAX_VIOLATOR_LINE)
                collector._get_last_violator.assert_called_with(self.fake_violator_line)


class ViolationCollectorPipelineTestCase(T.TestCase):

    class ViolatingTestCase(T.TestCase):
        def test_filesystem_violation(self):
            fd, fpath = tempfile.mkstemp(suffix="fake_testfile")
            os.close(fd)
            os.unlink(fpath)

        def test_network_violation(self):
            socket.gethostbyname("yelp.com")

    def test_violation_collector_pipeline(self):
        if not catbox:
            # Nothing to test here, catbox is not installed.
            pass

        with mock.patch("testify.plugins.violation_collector.collect") as collect:
            with mocked_store() as mock_store:
                collector = ViolationCollector()
                collector.store = mock_store

                reporter = ViolationReporter(violation_collector=collector)

                # Runing the test case inside catbox, we'll catch
                # violating syscalls and catbox will call our logger
                # function (collect)
                runner = T.test_runner.TestRunner(self.ViolatingTestCase, test_reporters=[reporter])
                run_in_catbox(runner.run, collect, [])

                assert collect.called
                violating_syscalls = [call[0][0] for call in collect.call_args_list]
                T.assert_in('open', violating_syscalls)
                T.assert_in('unlink', violating_syscalls)
                T.assert_in('socketcall', violating_syscalls)
