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
import logging
import sqlalchemy as SA
from testify import test_reporter

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json

import yaml
import time
import threading
import Queue

metadata = SA.MetaData()

Tests = SA.Table('tests', metadata,
    SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
    SA.Column('module', SA.String(255)),
    SA.Column('class_name', SA.String(255)),
    SA.Column('method_name', SA.String(255)),
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
    SA.Column('buildname', SA.String(40), nullable=False),
    SA.Column('branch', SA.String(255), index=True, nullable=False),
    SA.Column('revision', SA.String(40), index=True, nullable=False),
    SA.Column('end_time', SA.Integer, index=True, nullable=True),
    SA.Column('run_time', SA.Float, nullable=True),
    SA.Column('method_count', SA.Integer, nullable=True),
)
SA.Index('ix_individual_run', Builds.c.buildbot, Builds.c.buildname, Builds.c.buildnumber, Builds.c.revision, unique=True)

TestResults = SA.Table('test_results', metadata,
    SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
    SA.Column('test', SA.Integer, index=True, nullable=False),
    SA.Column('failure', SA.Integer, index=True),
    SA.Column('build', SA.Integer, index=True, nullable=False),
    SA.Column('end_time', SA.Integer, index=True, nullable=False),
    SA.Column('run_time', SA.Float, index=True, nullable=False),
    SA.Column('runner_id', SA.String(255), index=True, nullable=True),
    SA.Column('previous_run', SA.Integer, index=False, nullable=True),
)
SA.Index('ix_build_test_failure', TestResults.c.build, TestResults.c.test, TestResults.c.failure)

def md5(s):
    return hashlib.md5(s.encode('utf8') if isinstance(s, unicode) else s).hexdigest()

class SQLReporter(test_reporter.TestReporter):
    def __init__(self, options, *args, **kwargs):
        dburl = options.reporting_db_url or SA.engine.url.URL(**yaml.safe_load(open(options.reporting_db_config)))

        create_engine_opts = kwargs.pop('create_engine_opts', {
            'poolclass' : kwargs.pop('poolclass', SA.pool.NullPool),
            'pool_recycle' : 3600,
        })

        self.engine = SA.create_engine(dburl, **create_engine_opts)
        self.conn = self.engine.connect()
        metadata.create_all(self.engine)

        self.build_id = self.create_build_row(options.build_info)
        self.start_time = time.time()

        # Cache of (module,class_name,method_name) => test id
        self.test_id_cache = dict(
                ((row[Tests.c.module], row[Tests.c.class_name], row[Tests.c.method_name]), row[Tests.c.id])
                for row in self.conn.execute(Tests.select())
            )

        self.result_queue = Queue.Queue()
        self.ok = True

        self.reporting_frequency = options.sql_reporting_frequency
        self.batch_size = options.sql_batch_size

        self.reporting_thread = threading.Thread(target=self.report_results)
        self.reporting_thread.daemon = True
        self.reporting_thread.start()

        super(SQLReporter, self).__init__(options, *args, **kwargs)

    def create_build_row(self, build_info):
        if not build_info:
            raise ValueError("Build info must be specified when reporting to a database.")
        info_dict = json.loads(build_info)
        results = self.conn.execute(Builds.insert({
            'buildbot' : info_dict['buildbot'],
            'buildnumber' : info_dict['buildnumber'],
            'branch' : info_dict['branch'],
            'revision' : info_dict['revision'],
            'buildname' : info_dict['buildname'],
        }))
        return results.lastrowid

    def test_counts(self, test_case_count, test_method_count):
        """Store the number of tests so we can determine progress."""
        self.conn.execute(SA.update(Builds,
            whereclause=(Builds.c.id == self.build_id),
            values={
                'method_count' : test_method_count,
            }
        ))

    def test_complete(self, result):
        """Insert a result into the queue that report_results pulls from."""
        self.result_queue.put(result)

    def report_results(self):
        """A worker func that runs in another thread and reports results to the database.
        Create a TestResults row from a test result dict. Also inserts the previous_run row."""
        def create_row_to_insert(result, previous_run_id=None):
            return {
                'test' : get_test_id(result['method']['module'], result['method']['class'], result['method']['name']),
                'failure' : get_failure_id(result['exception_info']),
                'build' : self.build_id,
                'end_time' : result['end_time'],
                'run_time' : result['run_time'],
                'runner_id' : result['runner_id'],
                'previous_run' : previous_run_id,
            }

        def get_test_id(module, class_name, method_name):
            """Get the ID of the Tests row that corresponds to this test. If the row doesn't exist, insert one"""

            cached_result = self.test_id_cache.get((module, class_name, method_name), None)
            if cached_result is not None:
                return cached_result

            query = SA.select(
                [Tests.c.id],
                SA.and_(
                    Tests.c.module == module,
                    Tests.c.class_name == class_name,
                    Tests.c.method_name == method_name,
                )
            )

            # Most of the time, the Tests row will already exist for this test (it's been run before.)
            row = conn.execute(query).fetchone()
            if row:
                return row[Tests.c.id]
            else:
                # Not there (this test hasn't been run before); create it
                results = conn.execute(Tests.insert({
                    'module' : module,
                    'class_name' : class_name,
                    'method_name' : method_name,
                }))
                # and then return it.
                return results.lastrowid

        def get_failure_id(exception_info):
            """Get the ID of the failure row for the specified exception."""
            if not exception_info:
                return None
            exc_hash = md5(''.join(exception_info))

            query = SA.select(
                [Failures.c.id],
                Failures.c.hash == exc_hash,
            )
            row = conn.execute(query).fetchone()
            if row:
                return row[Failures.c.id]
            else:
                # We haven't inserted this row yet; insert it and re-query.
                results = conn.execute(Failures.insert({
                    'hash' : exc_hash,
                    'error' : exception_info[-1].strip(),
                    'traceback': ''.join(exception_info),
                }))
                return results.lastrowid

        def insert_single_run(result):
            """Recursively insert a run and its previous runs."""
            previous_run_id = insert_single_run(result['previous_run']) if result['previous_run'] else None
            results = conn.execute(TestResults.insert(create_row_to_insert(result, previous_run_id=previous_run_id)))
            return results.lastrowid

        conn = self.engine.connect()

        while True:
            results = []
            # Block until there's a result available.
            results.append(self.result_queue.get())
            # Grab any more tests that come in during the next self.reporting_frequency seconds.
            time.sleep(self.reporting_frequency)
            try:
                while True:
                    results.append(self.result_queue.get_nowait())
            except Queue.Empty:
                pass

            # Insert any previous runs, if necessary.
            for result in filter(lambda x: x['previous_run'], results):
                result['previous_run_id'] = insert_single_run(result['previous_run'])

            chunks = (results[i:i+self.batch_size] for i in xrange(0, len(results), self.batch_size))

            for chunk in chunks:
                try:
                    conn.execute(TestResults.insert(),
                        [create_row_to_insert(result, result.get('previous_run_id', None)) for result in chunk]
                    )
                except Exception, e:
                    logging.error("Exception while reporting results: " + repr(e))
                    self.ok = False
                finally:
                    # Do this in finally so we don't hang at report() time if we get errors.
                    for _ in xrange(len(chunk)):
                        self.result_queue.task_done()


    def report(self):
        self.end_time = time.time()
        self.result_queue.join()
        query = SA.update(Builds,
            whereclause=(Builds.c.id == self.build_id),
            values={
                'end_time' : self.end_time,
                'run_time' : self.end_time - self.start_time,
            }
        )
        self.conn.execute(query)
        return self.ok


# Hooks for plugin system
def add_command_line_options(parser):
    parser.add_option("--reporting-db-config", action="store", dest="reporting_db_config", type="string", default=None, help="Path to a yaml file describing the SQL database to report into.")
    parser.add_option('--reporting-db-url', action="store", dest="reporting_db_url", type="string", default=None, help="The URL of a SQL database to report into.")
    parser.add_option("--build-info", action="store", dest="build_info", type="string", default=None, help="A JSON dictionary of information about this build, to store in the reporting database.")
    parser.add_option("--sql-reporting-frequency", action="store", dest="sql_reporting_frequency", type="float", default=1.0, help="How long to wait between SQL inserts, at a minimum")
    parser.add_option("--sql-batch-size", action="store", dest="sql_batch_size", type="int", default="500", help="Maximum number of rows to insert at any one time")

def build_test_reporters(options):
    if options.reporting_db_config or options.reporting_db_url:
        return [SQLReporter(options)]
    else:
        return []