import os
import socket
import tempfile

import mock

import testify as T

from testify.plugins.violation_collector import cleandict
from testify.plugins.violation_collector import is_sqliteurl
from testify.plugins.violation_collector import sqlite_dbpath

from testify.plugins.violation_collector import collector
from testify.plugins.violation_collector import ViolationCollector
from testify.plugins.violation_collector import ViolationReporter
from testify.plugins.violation_collector import ViolationStore



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
        self.mock_collector = mock.Mock()
        self.mock_set_violator = mock.Mock()
        self.reporter = ViolationReporter(violation_collector=self.mock_collector)
        self.reporter.set_violator = self.mock_set_violator

    def test_test_case_start(self):
        self.reporter.test_case_start(self.mock_result)
        assert self.mock_set_violator
        assert self.mock_collector.store.add_test.called

    def test_test_case_complete(self):
        self.reporter.test_case_complete(self.mock_result)
        assert self.mock_collector.get_violator.called

    def test_test_start(self):
        self.reporter.test_start(self.mock_result)
        assert self.mock_set_violator
        assert self.mock_collector.store.add_test.called

    def test_test_complete(self):
        self.reporter.test_complete(self.mock_result)
        assert self.mock_collector.get_violator.called

    def test_test_setup_start(self):
        self.reporter.test_setup_start(self.mock_result)
        assert self.mock_set_violator
        assert self.mock_collector.store.add_test.called

    def test_test_setup_complete(self):
        self.reporter.test_setup_complete(self.mock_result)
        assert self.mock_collector.get_violator.called

    def test_test_teardown_start(self):
        self.reporter.test_teardown_start(self.mock_result)
        assert self.mock_set_violator
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

    def test_report(self):
        assert False, "TODO: implement test for ViolationReporter.report"


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

    def test_nothing(self):
        pass

