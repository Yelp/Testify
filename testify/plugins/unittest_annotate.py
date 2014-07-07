# Testify Unit TestAnnotation Plugin
# Requires: sqlalchemy, violations_collector plugin,
#           a fully formed database previously filled with data 
#           from the violations collector plugin
# 
# This plugin will find all test methods that do not make any system
# calls according to the information collected from the violations collector
# plugin. All test methods that do not make any system calls will then
# be categorized with the "unittest" suite.


import sqlalchemy as SA
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from testify import suite
import logging
import yaml

Base = declarative_base()


def add_command_line_options(parser):
    """Command line options for unittest annotation"""
    parser.add_option("--unittest-db-url", action="store",
    	dest="unittest_db_url", type="string",
        default='sqlite:///unittest.db',
        help="Path to the violations db for unittest id")

    parser.add_option("--unittest-db-config", action="store",
    	dest="unittest_db_config", type="string",
        help="Path to a config file for violations db info")


def prepare_test_runner(options, runner):
    """Add data structure to runner for future use"""
    runner.unittests = {}
    db = Database(options)
    try:
        runner.unittests = db.build_dict()

    except SA.exc.OperationalError:
        logging.error('TESTIFY ERROR: db could not be accessed')
        logging.info('the database may not be running or incorrect config information was given')


def add_testcase_info(test_case, runner):
    """Uses the runner's data structure to add information about tests"""
    test_case.unittests = []

    if not hasattr(runner, 'unittests'):
        # In some acceptance tests, the plugin will be run without being properly prepared
        # This will occur for partial runs
        return


    for test_method in test_case.runnable_test_methods():
        # Check if method is runnable
        test_name = runner.get_test_method_name(test_method)

        try:
            if runner.unittests[test_name]:
                test_method = suite('unittest')(test_method.__func__)


        except KeyError:
            # This test has never been in nightly - don't know if unit
            pass


def find_db_url(options):
    if options.unittest_db_config:
        # Read in the yaml file
        with open(options.unittest_db_config) as db_config_file:
            return SA.engine.url.URL(**yaml.safe_load(db_config_file))

    elif options.violation_dbconfig:
        # Read in the yaml file
        with open(options.violation_dbconfig) as db_config_file:
            return SA.engine.url.URL(**yaml.safe_load(db_config_file))

    elif options.violation_dburl:
        return options.violation_dburl

    elif options.unittest_db_url:
        return options.unittest_db_url

    else:
        raise ValueError('No database was found for unittest annotation')


class Database(object):

    def __init__(self, options):
        url = find_db_url(options)

        self.engine = SA.create_engine(url)

        Session = SA.orm.sessionmaker()
        Session.configure(bind=self.engine)
        self.session = Session()

        self.unittest = {}

    def last_time_of_catbox_run(self):
        """Grabs timestamp of last nightly build from catbox"""
        return self.session.query(SA.func.max(Denormalized.start_time)) \
                           .scalar()

    def buildbot_run_id(self, last_time):
        """Finds run id from timestamp"""
        return self.session.query(Denormalized) \
                           .filter(Denormalized.start_time == last_time) \
                           .first().buildbot_run_id

    def all_tests(self, buildbot_run):
        """Returns all tests in run"""
        return self.session.query(Methods) \
                           .filter(Methods.buildbot_run_id == buildbot_run) \
                           .all()

    def all_violating_tests(self, buildbot_run):
        """Returns all non-unit tests (not setup, teardown)"""
        return self.session.query(Methods) \
                           .filter(Methods.method_type == 'test') \
                           .join(Violations).all()

    def build_dict(self):
        """ Builds a data structure to help find unit tests from violations info

        Structure format: self.unittest[test_name] -> is test_name a unit test? (boolean)
        """

        last_time = self.last_time_of_catbox_run()
        bb_runid = self.buildbot_run_id(last_time)

        all_tests = self.all_tests(bb_runid)
        all_violates = self.all_violating_tests(bb_runid)

        for test in all_tests:
            #Unit until proven not
            test_name = "%s %s.%s" % (test.module,
            	test.class_name, test.method_name)

            self.unittest[test_name] = True

        for test in all_violates:
            # Methods that are not unit tests
            test_name = "%s %s.%s" % (test.module,
            	test.class_name, test.method_name)

            self.unittest[test_name] = False

        return self.unittest


class Denormalized(Base):
    __tablename__ = 'catbox_denormalized_builds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    buildbot_run_id = Column(String, nullable=True)
    branch = Column(String, nullable=True)
    revision = Column(String, nullable=True)
    start_time = Column(Integer, nullable=True)


class Methods(Base):
    __tablename__ = 'catbox_methods'

    id = Column(Integer, primary_key=True, autoincrement=True)
    buildbot_run_id = Column(String, index=True,  nullable=True)
    branch = Column(Text)
    revision = Column(Text)
    start_time = Column(Integer)
    module = Column(Text, nullable=False)
    class_name = Column(Text, nullable=False)
    method_name = Column(Text, nullable=False)
    method_type = Column(Enum('undefined', 'test', 'setup',
                              'teardown', 'class_setup', 'class_teardown'),
                         nullable=False)


class Violations(Base):
    __tablename__ = 'catbox_violations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(Integer, ForeignKey('catbox_methods.id'))
    syscall = Column(String, nullable=False)
    syscall_args = Column(Text, nullable=True)
    start_time = Column(Integer)
