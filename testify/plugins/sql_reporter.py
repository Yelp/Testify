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

SA = None
try:
    import sqlalchemy as SA
except ImportError:
    pass

from testify import test_reporter

def md5(s):
    return hashlib.md5(s.encode('utf8') if isinstance(s, unicode) else s).hexdigest()


class SQLReporter(test_reporter.TestReporter):

    def __init__(self, options, *args, **kwargs):
        dburl = options.reporting_db_url or SA.engine.url.URL(**yaml.safe_load(open(options.reporting_db_config)))

        create_engine_opts = kwargs.pop('create_engine_opts', {
            'poolclass' : kwargs.pop('poolclass', SA.pool.NullPool),
            'pool_recycle' : 3600,
        })

        self.retry_period = kwargs.pop('retry_period', 1)
        self.retry_limit = kwargs.pop('retry_limit', 300)
        self.retry_backoff = kwargs.pop('retry_backoff', 1)

        self.init_database()
        self.engine = SA.create_engine(dburl, **create_engine_opts)
        self.conn = self._connect()
        self.metadata.create_all(self.engine)

        if not options.build_info:
            raise ValueError("Build info must be specified when reporting to a database.")
        
        build_info_dict = json.loads(options.build_info)
        self.build_id = self.create_build_row(build_info_dict)
        self.start_time = time.time()

        # Cache of (module,class_name,method_name) => test id
        self.test_id_cache = dict(
                ((row[self.Tests.c.module], row[self.Tests.c.class_name], row[self.Tests.c.method_name]), row[self.Tests.c.id])
                for row in self.conn.execute(self.Tests.select())
            )

        self.result_queue = Queue.Queue()
        self.ok = True

        self.reporting_frequency = options.sql_reporting_frequency
        self.batch_size = options.sql_batch_size

        self.reporting_thread = threading.Thread(target=self.report_results)
        self.reporting_thread.daemon = True
        self.reporting_thread.start()

        super(SQLReporter, self).__init__(options, *args, **kwargs)

    def _connect(self):
        """Return an SA connection, based on self.engine.
        The connection will be retried a limited number of times if necessary.
        """
        wait = self.retry_period
        limit = self.retry_limit

        while True:
            try:
                return self.engine.connect()
            except SA.exc.OperationalError:
                if limit <= 0:
                    raise
                else:
                    print 'SQL connection failed, retrying in %g seconds (giving up in %g seconds)...' % (wait, limit)
                    time.sleep(min(wait, limit))
                    limit -= wait
                    wait += self.retry_backoff

    def init_database(self):
        self.metadata = SA.MetaData()

        self.Tests = SA.Table('tests', self.metadata,
            SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
            SA.Column('module', SA.String(255)),
            SA.Column('class_name', SA.String(255)),
            SA.Column('method_name', SA.String(255)),
        )
        SA.Index('ix_individual_test', self.Tests.c.module, self.Tests.c.class_name, self.Tests.c.method_name, unique=True)

        self.Failures = SA.Table('failures', self.metadata,
            SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
            SA.Column('error', SA.Text, nullable=False),
            SA.Column('traceback', SA.Text, nullable=False),
            SA.Column('hash', SA.String(40), unique=True, nullable=False),
        )

        self.Builds = SA.Table('builds', self.metadata,
            SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
            SA.Column('buildbot_run_id', SA.String(36), index=True, nullable=True),
            SA.Column('buildbot', SA.Integer, nullable=False),
            SA.Column('buildnumber', SA.Integer, nullable=False),
            SA.Column('buildname', SA.String(40), nullable=False),
            SA.Column('branch', SA.String(255), index=True, nullable=False),
            SA.Column('revision', SA.String(40), index=True, nullable=False),
            SA.Column('end_time', SA.Integer, index=True, nullable=True),
            SA.Column('run_time', SA.Float, nullable=True),
            SA.Column('method_count', SA.Integer, nullable=True),
            SA.Column('submit_time', SA.Integer, index=True, nullable=True),
            SA.Column('discovery_failure', SA.Boolean, default=False, nullable=True),
        )
        SA.Index('ix_individual_run', self.Builds.c.buildbot, self.Builds.c.buildname, self.Builds.c.buildnumber, self.Builds.c.revision, unique=True)

        self.TestResults = SA.Table('test_results', self.metadata,
            SA.Column('id', SA.Integer, primary_key=True, autoincrement=True),
            SA.Column('test', SA.Integer, index=True, nullable=False),
            SA.Column('failure', SA.Integer, index=True),
            SA.Column('build', SA.Integer, index=True, nullable=False),
            SA.Column('end_time', SA.Integer, index=True, nullable=False),
            SA.Column('run_time', SA.Float, index=True, nullable=False),
            SA.Column('runner_id', SA.String(255), index=True, nullable=True),
            SA.Column('previous_run', SA.Integer, index=False, nullable=True),
        )
        SA.Index('ix_build_test_failure', self.TestResults.c.build, self.TestResults.c.test, self.TestResults.c.failure)


    def create_build_row(self, info_dict):
        results = self.conn.execute(self.Builds.insert({
            'buildbot_run_id' : info_dict['buildbot_run_id'],
            'buildbot' : info_dict['buildbot'],
            'buildnumber' : info_dict['buildnumber'],
            'branch' : info_dict['branch'],
            'revision' : info_dict['revision'],
            'submit_time' : info_dict.get('submitstamp'),
            'buildname' : info_dict['buildname'],
        }))
        return results.lastrowid

    def test_counts(self, test_case_count, test_method_count):
        """Store the number of tests so we can determine progress."""
        self.conn.execute(SA.update(self.Builds,
            whereclause=(self.Builds.c.id == self.build_id),
            values={
                'method_count' : test_method_count,
            }
        ))

    def class_teardown_complete(self, result):
        """If there was an error during class_teardown, insert the result
        containing the error into the queue that report_results pulls from.
        """
        if not result['success']:
            self.result_queue.put(result)

    def test_complete(self, result):
        """Insert a result into the queue that report_results pulls from."""
        # Test methods named 'run' are special. See TestCase.run().
        if not result['method']['name'] == 'run':
            self.result_queue.put(result)

    def test_discovery_failure(self, exc):
        """Set the discovery_failure flag to True and method_count to 0."""
        self.conn.execute(SA.update(self.Builds,
            whereclause=(self.Builds.c.id == self.build_id),
            values={
                'discovery_failure' : True,
                'method_count' : 0,
            }
        ))

    def _canonicalize_exception(self, traceback, error):
        error = error.strip()
        if self.options.sql_traceback_size is not None:
            truncation_message = " (Exception truncated.)"
            size_limit = self.options.sql_traceback_size - len(truncation_message)
            if len(traceback) > self.options.sql_traceback_size:
                traceback = traceback[:size_limit] + truncation_message
            if len(error) > self.options.sql_traceback_size:
                error = error[:size_limit] + truncation_message

        return (traceback, error)

    def _create_row_to_insert(self, conn, result, previous_run_id=None):
        return {
            'test' : self._get_test_id(conn, result['method']['module'], result['method']['class'], result['method']['name']),
            'failure' : self._get_failure_id(conn, result['exception_info'], result['exception_only']),
            'build' : self.build_id,
            'end_time' : result['end_time'],
            'run_time' : result['run_time'],
            'runner_id' : result['runner_id'],
            'previous_run' : previous_run_id,
        }

    def _get_test_id(self, conn, module, class_name, method_name):
        """Get the ID of the self.Tests row that corresponds to this test. If the row doesn't exist, insert one"""

        cached_result = self.test_id_cache.get((module, class_name, method_name), None)
        if cached_result is not None:
            return cached_result

        query = SA.select(
            [self.Tests.c.id],
            SA.and_(
                self.Tests.c.module == module,
                self.Tests.c.class_name == class_name,
                self.Tests.c.method_name == method_name,
            )
        )

        # Most of the time, the self.Tests row will already exist for this test (it's been run before.)
        row = conn.execute(query).fetchone()
        if row:
            return row[self.Tests.c.id]
        else:
            # Not there (this test hasn't been run before); create it
            results = conn.execute(self.Tests.insert({
                'module' : module,
                'class_name' : class_name,
                'method_name' : method_name,
            }))
            # and then return it.
            return results.lastrowid

    def _get_failure_id(self, conn, exception_info, error):
        """Get the ID of the failure row for the specified exception."""
        if not exception_info:
            return None

        # Canonicalize the traceback and error for storage.
        traceback, error = self._canonicalize_exception(exception_info, error)

        exc_hash = md5(traceback)

        query = SA.select(
            [self.Failures.c.id],
            self.Failures.c.hash == exc_hash,
        )
        row = conn.execute(query).fetchone()
        if row:
            return row[self.Failures.c.id]
        else:
            # We haven't inserted this row yet; insert it and re-query.
            results = conn.execute(self.Failures.insert({
                'hash' : exc_hash,
                'error' : error,
                'traceback': traceback,
            }))
            return results.lastrowid

    def _insert_single_run(self, conn, result):
        """Recursively insert a run and its previous runs."""
        previous_run_id = self._insert_single_run(conn, result['previous_run']) if result['previous_run'] else None
        results = conn.execute(self.TestResults.insert(self._create_row_to_insert(conn, result, previous_run_id=previous_run_id)))
        return results.lastrowid

    def _report_results_by_chunk(self, conn, chunk):
        try:
            conn.execute(self.TestResults.insert(),
                [self._create_row_to_insert(conn, result, result.get('previous_run_id', None)) for result in chunk]
            )
        except Exception, e:
            logging.exception("Exception while reporting results: " + repr(e))
            self.ok = False
        finally:
            # Do this in finally so we don't hang at report() time if we get errors.
            for _ in xrange(len(chunk)):
                self.result_queue.task_done()

    def report_results(self):
        """A worker func that runs in another thread and reports results to the database.
        Create a self.TestResults row from a test result dict. Also inserts the previous_run row."""
        conn = self._connect()

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
                try:
                    result['previous_run_id'] = self._insert_single_run(conn, result['previous_run'])
                except Exception, e:
                    logging.exception("Exception while reporting results: " + repr(e))
                    self.ok = False

            chunks = (results[i:i+self.batch_size] for i in xrange(0, len(results), self.batch_size))

            for chunk in chunks:
                self._report_results_by_chunk(conn, chunk)

    def report(self):
        self.end_time = time.time()
        self.result_queue.join()
        query = SA.update(self.Builds,
            whereclause=(self.Builds.c.id == self.build_id),
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
    parser.add_option("--sql-traceback-size", action="store", dest="sql_traceback_size", type="int", default="65536", help="Maximum length of traceback to store. Tracebacks longer than this will be truncated.")

def build_test_reporters(options):
    if options.reporting_db_config or options.reporting_db_url:
        if not SA:
            msg = 'SQL Reporter plugin requires sqlalchemy and you do not have it installed in your PYTHONPATH.\n'
            raise ImportError, msg
        return [SQLReporter(options)]
    return []

# vim: set ts=4 sts=4 sw=4 et:
