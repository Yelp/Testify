# Copyright 2009 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib
import sqlalchemy as SA
from sqlalchemy.orm.exc import NoResultFound
from testify import test_reporter

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json

metadata = SA.MetaData()

Tests = SA.Table('tests', metadata,
    SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
    SA.Column('module', SA.String(100)),
    SA.Column('class_name', SA.String(100)),
    SA.Column('method_name', SA.String(100)),
)
SA.Index('ix_individual_test', Tests.c.module, Tests.c.class_name, Tests.c.method_name, unique=True)

Failures = SA.Table('failures', metadata,
    SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
    SA.Column('error', SA.Text, nullable=False),
    SA.Column('traceback', SA.Text, nullable=False),
    SA.Column('hash', SA.String(40), unique=True, nullable=False),
)

Builds = SA.Table('builds', metadata,
    SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
    SA.Column('buildbot', SA.Integer, nullable=False),
    SA.Column('buildnumber', SA.Integer, nullable=False),
    SA.Column('branch', SA.String(100), index=True, nullable=False),
    SA.Column('revision', SA.String(40), index=True, nullable=False),
    SA.Column('end_time', SA.Integer, index=True, nullable=True),
    SA.Column('run_time', SA.Integer, nullable=True),
    # SA.Column('errored', SA.Integer, nullable=False),
)
SA.Index('ix_individual_run', Builds.c.buildbot, Builds.c.buildnumber, Builds.c.revision, unique=True)

BUILD_NOT_ERRORED = 0
BUILD_ERRORED = 1
BUILD_IN_PROGRESS = 2

TestResults = SA.Table('test_results', metadata,
    SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
    SA.Column('test', SA.Integer, index=True, nullable=False),
    SA.Column('failure', SA.Integer, index=True),
    SA.Column('build', SA.Integer, index=True, nullable=False),
    SA.Column('end_time', SA.Integer, index=True, nullable=False),
    SA.Column('run_time', SA.Integer, index=True, nullable=False),
    SA.Column('runner_id', SA.String(100), index=True, nullable=True),
    SA.Column('previous_run', SA.Integer, index=False, nullable=True),
)
SA.Index('ix_build_tests', TestResults.c.test, TestResults.c.build, unique=True)


def md5(str):
    return hashlib.md5(str.encode('utf8')).hexdigest()

class SQLReporter(test_reporter.TestReporter):
    def __init__(self, options, *args, **kwargs):
        engine = SA.create_engine(options.reporting_db, poolclass=SA.pool.NullPool, pool_recycle=3600)
        self.conn = engine.connect()
        metadata.create_all(engine)

        self.build_id = self.create_build_row(options.build_info)

        super(SQLReporter, self).__init__(options, *args, **kwargs)

    def create_build_row(self, build_info):
        if not build_info:
            raise ValueError("Build info must be specified when reporting to a database.")
        info_dict = json.loads(build_info)
        self.conn.execute(Builds.insert({
            'buildbot' : info_dict['buildbot'],
            'buildnumber' : info_dict['buildnumber'],
            'branch' : info_dict['branch'],
            'revision' : info_dict['revision'],
        }))
        results = self.conn.execute(SA.select(
            [Builds.c.id],
            SA.and_(
                Builds.c.buildbot == info_dict['buildbot'],
                Builds.c.buildnumber == info_dict['buildnumber'],
                Builds.c.revision == info_dict['revision'],
            )
        ))
        return results.fetchone()[Builds.c.id]

    def test_complete(self, result):
        """Create a TestResults row from a test result dict. Also inserts the previous_run row."""
        def create_row_to_insert(result, previous_run_id=None):
            return {
                'test' : self.get_test_id(result['method']['module'], result['method']['class'], result['method']['name']),
                'failure' : self.get_failure_id(result['exception_info']),
                'build' : self.build_id,
                'end_time' : result['end_time'],
                'run_time' : result['run_time'],
                'runner_id' : result['runner_id'],
                'previous_run' : previous_run_id,
            }

        if result['previous_run']:
            query = TestResults.insert(create_row_to_insert(result['previous_run']), returning=TestResults.c.id)
            results = self.conn.execute(query)
            previous_run_id = results.fetchone()
        else:
            previous_run_id = None

        self.conn.execute(TestResults.insert(create_row_to_insert(result, previous_run_id)))

    def get_test_id(self, module, class_name, method_name):
        """Get the ID of the Tests row that corresponds to this test. If the row doesn't exist, insert one"""

        query = SA.select(
            [Tests.c.id],
            SA.and_(
                Tests.c.module == module,
                Tests.c.class_name == class_name,
                Tests.c.method_name == method_name,
            )
        )

        # Most of the time, the Tests row will already exist for this test (it's been run before.)
        row = self.conn.execute(query).fetchone()
        if row:
            print "Test %d found" % row[Tests.c.id]
            return row[Tests.c.id]
        else:
            # Not there (this test hasn't been run before); create it
            self.conn.execute(Tests.insert({
                'module' : module,
                'class_name' : class_name,
                'method_name' : method_name,
            }))
            # and then return it.
            return self.conn.execute(query).fetchone()[Tests.c.id]

    def get_failure_id(self, exception_info):
        """Get the ID of the failure row for the specified exception."""
        if not exception_info:
            return None
        exc_hash = md5(''.join(exception_info))
        self.conn.execute(Failures.insert({
            'hash' : exc_hash,
            'error' : exception_info[0],
            'traceback': ''.join(exception_info),
        }))

        query = SA.select(
            [Failures.c.id],
            Failures.c.hash == exc_hash,
        )
        results = self.conn.execute(query)

        return results.fetchone()[Failures.c.id]

    def report(self):
        #TODO update end_time, duration.
        return True


# Hooks for plugin system
def add_command_line_options(parser):
    parser.add_option("--reporting-db", action="store", dest="reporting_db", type="string", default=None, help="URL of SQL database to report into. In the form dialect://user:password@host/dbname[?key=value..]")
    parser.add_option("--build-info", action="store", dest="build_info", type="string", default=None, help="A JSON dictionary of information about this build, to store in the reporting database.")

def build_test_reporters(options):
    if options.reporting_db:
        return [SQLReporter(options)]
    else:
        return []


