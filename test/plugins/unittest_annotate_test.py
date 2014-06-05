import testify
import tempfile
import sqlalchemy
import mock
import os
from testify.plugins.unittest_annotate import Database
from testify.plugins.unittest_annotate import Denormalized
from testify.plugins.unittest_annotate import Methods
from testify.plugins.unittest_annotate import Violations
from testify.plugins.unittest_annotate import find_db_url
from testify.plugins.unittest_annotate import add_testcase_info
from testify.test_case import TestCase
from testify.test_runner import TestRunner
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String

class DummyClass(object):
    pass

class DatabaseTestCase(testify.TestCase):
    """Tests for the Database class"""

    @testify.class_setup
    def setup(self):
        self.url = 'sqlite:///unittest.db'
        self.engine = sqlalchemy.create_engine(self.url)

        Session = sqlalchemy.orm.sessionmaker(bind=self.engine)

        self.session = Session()
        self.options_db = DummyClass()
        self.options_db.unittest_db_url = self.url
        self.options_db.unittest_db_config = None
        self.options_db.violation_dburl = None
        self.options_db.violation_dbconfig = None

        if not self.engine.has_table(Denormalized.__tablename__):
            Denormalized.__table__.create(self.engine)

        if not self.engine.has_table(Methods.__tablename__):
            Methods.__table__.create(self.engine)

        if not self.engine.has_table(Violations.__tablename__):
            Violations.__table__.create(self.engine)

    @testify.setup
    def fixtures(self):
        # Build denormalized table
        times = xrange(1,10)
        for time in times:
            bb_runid = str(time)
            build = Denormalized(buildbot_run_id=bb_runid,
                                 branch='test_branch',
                                 revision='test_rev',
                                 start_time=time)
            self.session.add(build)
            self.session.commit()

        # Build methods table
        for time in times:
            bb_runid = 9
            method_type = 'undefined'
            if time == 2 or time == 3:
                # Undefined with Violations
                method_type = 'test'
            method = Methods(buildbot_run_id=bb_runid,
                branch=u"test",
                revision=u"test",
                start_time=0,
                module=u'test',
                class_name=u'test' + unicode(time),
                method_name=u'test' + unicode(time),
                method_type=method_type)
            self.session.add(method)
            self.session.commit()
        
        for time in times:
            testid = 100
            if time == 1 or time == 2 or time == 3:
                testid = time
            violation = Violations(test_id=testid,
                syscall='test',
                syscall_args='test',
                start_time=123)
            self.session.add(violation)
            self.session.commit()
                
    @testify.teardown
    def teardown(self):
        self.session.query(Denormalized).delete()
        self.session.commit()

        self.session.query(Methods).delete()
        self.session.commit()

        self.session.query(Violations).delete()
        self.session.commit()

        self.options_db.unittest_db_url = self.url
        self.options_db.unittest_db_config = None
        self.options_db.violation_dburl = None
        self.options_db.violation_dbconfig = None

    @testify.class_teardown
    def close(self):
        self.session.close()
        os.remove('unittest.db')

    def test_last_time(self):
        db_class = Database(self.options_db)
        last_time = db_class.last_time()
        
        # Find actual last time
        self.assertEqual(last_time, max(range(1,10)))

    def test_bb_run_id(self):
        # We know that 9 is max_time
        max_time = 9
        db_class = Database(self.options_db)
        bb_runid = db_class.buildbot_run_id(max_time)

        self.assertEqual(bb_runid, str(max_time))

    def test_all_tests(self):
        db_class = Database(self.options_db)
        all_tests = db_class.all_tests(9)
        self.assertEqual(len(all_tests), 9)

        
    def test_violations(self):
        max_time = 9
        db_class = Database(self.options_db)

        all_violating_tests = db_class.all_violating_tests(max_time)
        self.assertEqual(len(all_violating_tests), 2)        

        for test in all_violating_tests:
            self.assertEqual(test.method_type, 'test')

    def test_build_dict(self):
        """Test that the data structure is correct"""
        # Build the proper data structure
        proper_response = {}
        for test in range(1,10):
            test_name_part = u'test' + unicode(test)
            name = "%s %s.%s" % (u'test', test_name_part, test_name_part)
            if test == 2 or test == 3:
                proper_response[name] = False
            else:
                proper_response[name] = True

        db_class = Database(self.options_db)
        unittest = db_class.build_dict()
        self.assertEqual(unittest, proper_response)

    def test_find_db_url(self):
        # Check for unittest_db_url
        db_url = 'test/test'
        self.options_db.unittest_db_url = db_url

        self.assertEqual(db_url, find_db_url(self.options_db))

    def test_find_violation_url(self):
        # Check for violation_db_url
        db_url = 'sqlite:///test2.db'
        self.options_db.violation_dburl = db_url

        self.assertEqual(db_url, find_db_url(self.options_db))

    def test_get_violation_with_dbconfig(self):
        self.options_db.violation_dburl = 'sqlite:///fake/database'
        self.options_db.violation_dbconfig = '/fake/path/to/db/'
                                                                  
        mocked_open = mock.Mock(spec=file)
        mocked_open.__enter__ = mock.Mock()
        mocked_open.__exit__ = mock.Mock()
        with mock.patch(
        'testify.plugins.unittest_annotate.open',
        create=True,
        return_value=mocked_open
        ):
            with mock.patch.object(sqlalchemy.engine.url, 'URL') as mocked_sa_url:
                testify.assert_not_equal(find_db_url(self.options_db), self.options_db.violation_dburl)
                mocked_open.read.assert_called
                mocked_sa_url.URL.assert_called

    def test_get_unittest_with_dbconfig(self):
        self.options_db.unittest_db_url = 'sqlite:///fake/database'
        self.options_db.unittest_db_config = '/fake/path/to/db/'
                                                                  
        mocked_open = mock.Mock(spec=file)
        mocked_open.__enter__ = mock.Mock()
        mocked_open.__exit__ = mock.Mock()
        with mock.patch(
        'testify.plugins.unittest_annotate.open',
        create=True,
        return_value=mocked_open
        ):
            with mock.patch.object(sqlalchemy.engine.url, 'URL') as mocked_sa_url:
                testify.assert_not_equal(find_db_url(self.options_db), self.options_db.unittest_db_url)
                mocked_open.read.assert_called
                mocked_sa_url.URL.assert_called

    @mock.patch('testify.test_case.TestCase.runnable_test_methods')
    def test_add_testcase_info(self, mock_methods):
        # Build a fake runner
        test_case = TestCase()
        runner = TestRunner(test_case)
        
        # Populate runner with fake structure
        runner.unittests = {}
        runner.unittests['mod class.test1'] = True
        runner.unittests['mod class.test2'] = False

        # Populate fake test_case with 3 fake methods
        test_methods = []
        for test in xrange(1,4):
            test_method = mock.Mock()
            test_method.im_class.__module__ = 'mod'
            test_method.im_class.__name__ = 'class'
            test_method.__name__ = 'test' + str(test)
            test_methods.append(test_method)

        # Run add_testcase_info
        mock_methods.return_value = test_methods
        add_testcase_info(test_case, runner)
        
        # Verify that unittests work
        self.assertEqual(len(test_case.unittests), 1)
        
        
        
