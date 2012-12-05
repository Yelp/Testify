import os

import testify as T
from testify.plugins.violation_collector import cleandict
from testify.plugins.violation_collector import is_sqliteurl
from testify.plugins.violation_collector import sqlite_dbpath


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

class ViolationCollectorTestCase(T.TestCase):
    pass
