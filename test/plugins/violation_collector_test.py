import os
import socket
import tempfile

import mock

import testify as T

from testify.plugins.violation_collector import cleandict
from testify.plugins.violation_collector import collect
from testify.plugins.violation_collector import is_sqliteurl
from testify.plugins.violation_collector import sqlite_dbpath
from testify.plugins.violation_collector import ViolationReporter



class HelpersTestCase(T.TestCase):
    def test_is_sqliteurl(self):
        assert is_sqliteurl("sqlite://")
        assert is_sqliteurl("sqlite:///test.db")
        assert is_sqliteurl("sqlite:////tmp/test-database.sqlite")

    def test_sqlite_dbpath(self):
        T.assert_equal(sqlite_dbpath("sqlite:///test.sqlite"), os.path.abspath("test.sqlite"))
        T.assert_equal(sqlite_dbpath("sqlite:////var/tmp/test.sqlite"), "/var/tmp/test.sqlite")

    def test_cleandict(self):
        dirty_dict = {'a': 1, 'b': 2, 'c': 3}
        clean_dict = {'a': 1}
        T.assert_equal(cleandict(dirty_dict, allowed_keys=['a']), clean_dict)


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
        self.mock_store.violation_counts.return_value = []

        self.reporter.report()

        self.mock_collector.writeln.assert_called_with(
            "No unit test violations! \o/\n",
            T.test_logger.VERBOSITY_SILENT
        )

    def test_report_with_violations(self):
        fake_violation = [
            ('fake_class1', 'fake_method1', 'fake_violation1', 5),
        ]
        self.mock_store.violation_counts.return_value = fake_violation

        self.reporter.report()

        self.mock_collector.writeln.assert_called_with(
            "%s.%s\t%s\t%s" % fake_violation[0],
            T.test_logger.VERBOSITY_SILENT
        )


class ViolationCollectorTestCase(T.TestCase):

    class FakeViolatingTestCase(T.TestCase):
        def test_filesystem_violation(self):
            fd, fpath = tempfile.mkstemp(suffix="fake_testfile")
            os.close(fd)
            os.unlink(fpath)

        def test_network_violation(self):
            socket.gethostbyname("yelp.com")

    @T.setup
    def setup_testify_program(self):
        pass

    def test_violation_collector_pipeline(self):
        assert False, "Setup the whole pipeline and check if creating a violation is catched"

    def test_collect(self):
        with mock.patch('testify.plugins.violation_collector.collector') as mock_collector:
            mock_collector.get_violator.return_value = "fake_class1,fake_method1,tests.fake_module1"

            collect("fake_violation1", "", "")

            assert mock_collector.get_violator.called
            assert mock_collector.report_violation.called
            T.assert_equal(mock_collector.writeln.called, False)
