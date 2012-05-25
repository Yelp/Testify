"""
Client-server setup to evenly distribute tests across multiple processes. The server
discovers all test classes and enqueues them, then clients connect to the server,
receive tests to run, and send back their results.

The server keeps track of the overall status of the run and manages timeouts and retries.
"""

from __future__ import with_statement

from test_runner import TestRunner
import tornado.httpserver
import tornado.ioloop
import tornado.web

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json
import logging

import Queue
import time
import itertools
import threading


class AsyncQueue(object):
    def __init__(self):
        self.lock = threading.RLock()
        self.data_queue = Queue.PriorityQueue()
        self.callback_queue = Queue.PriorityQueue()
        self.finalized = False
        self._insert_count = 0

    def insert_count(self):
        self._insert_count += 1
        return self._insert_count

    def get(self, c_priority, callback):
        """If the queue is not empty, call callback immediately with the next item. Otherwise, put callback in a callback priority queue, to be called when data is put().
        If finalize() is called before data arrives for callback, callback(None, None) is called."""

        if self.finalized:
            callback(None, None)
            return
        try:
            self.lock.acquire()
            d_priority, _, data = self.data_queue.get_nowait()
            self.lock.release()  # Gets skipped if get_nowait raises Empty
            callback(d_priority, data)
        except Queue.Empty:
            self.callback_queue.put((c_priority, self.insert_count(), callback,))
            self.lock.release()

    def put(self, d_priority, data):
        """If a get callback is waiting, call it immediately with this data. Otherwise, put data in a priority queue, to be retrieved at a future date."""
        try:
            self.lock.acquire()
            c_priority, _, callback = self.callback_queue.get_nowait()
            self.lock.release()  # Gets skipped if get_nowait raises Empty
            callback(d_priority, data)
        except Queue.Empty:
            self.data_queue.put((d_priority, self.insert_count(), data,))
            self.lock.release()

    def empty(self):
        return self.data_queue.empty()

    def waiting(self):
        return not self.callback_queue.empty()

    def finalize(self):
        """Call all queued callbacks with None, and make sure any future calls to get() immediately call their callback with None."""
        self.finalized = True
        try:
            while True:
                with self.lock:
                    _, _, callback = self.callback_queue.get_nowait()
                callback(None, None)
        except Queue.Empty:
            pass


class TestRunnerServer(TestRunner):
    def __init__(self, *args, **kwargs):
        self.serve_port = kwargs.pop('serve_port')
        self.runner_timeout = kwargs['options'].runner_timeout
        self.revision = kwargs['options'].revision
        self.server_timeout = kwargs['options'].server_timeout
        self.shutdown_delay_for_connection_close = kwargs['options'].shutdown_delay_for_connection_close
        self.shutdown_delay_for_outstanding_runners = kwargs['options'].shutdown_delay_for_outstanding_runners

        self.test_queue = AsyncQueue()
        self.checked_out = {}  # Keyed on class path (module class).
        self.failed_rerun_methods = set()  # Set of (class_path, method) who have failed.
        self.timeout_rerun_methods = set()  # Set of (class_path, method) who were sent to a client but results never came.
        self.previous_run_results = {}  # Keyed on (class_path, method), values are result dictionaries.
        self.runners = set()  # The set of runner_ids who have asked for tests.
        self.runners_outstanding = set()  # The set of runners who have posted results but haven't asked for the next test yet.
        self.shutting_down = False  # Whether shutdown() has been called.
        self.fixtures_for_class = {}  # Keyed on class_path, stores a list of class_setup/class_teardown fixtures that a class should run. Used for requeuing.
        self.fixture_method_types = {}  # Keyed on (class_path, method), stores the fixture type of each fixture method.
        super(TestRunnerServer, self).__init__(*args, **kwargs)

    def get_next_test(self, runner_id, on_test_callback, on_empty_callback):
        """Enqueue a callback (which should take one argument, a test_dict) to be called when the next test is available."""

        self.runners.add(runner_id)

        def callback(priority, test_dict):
            if not test_dict:
                return on_empty_callback()

            if test_dict.get('last_runner', None) != runner_id or (self.test_queue.empty() and len(self.runners) <= 1):
                self.check_out_class(runner_id, test_dict)
                on_test_callback(test_dict)
            else:
                if self.test_queue.empty():
                    # Put the test back in the queue, and queue ourselves to pick up the next test queued.
                    self.test_queue.put(priority, test_dict)
                    self.test_queue.callback_queue.put((-1, callback))
                else:
                    # Get the next test, process it, then place the old test back in the queue.
                    self.test_queue.get(0, callback)
                    self.test_queue.put(priority, test_dict)

        self.test_queue.get(0, callback)

    def report_result(self, runner_id, result):
        class_path = '%s %s' % (result['method']['module'], result['method']['class'])
        d = self.checked_out.get(class_path)

        if not d:
            raise ValueError("Class %s not checked out." % class_path)
        if d['runner'] != runner_id:
            raise ValueError("Class %s checked out by runner %s, not %s" % (class_path, d['runner'], runner_id))

        if not result['method']['fixture_type']:
            # Test method.
            if result['method']['name'] not in d['test_methods']:
                raise ValueError("Method %s not checked out by runner %s." % (result['method']['name'], runner_id))

            if result['success']:
                d['passed_methods'][result['method']['name']] = result
            else:
                d['failed_methods'][result['method']['name']] = result
                self.failure_count += 1
                if self.failure_limit and self.failure_count >= self.failure_limit:
                    logging.error('Too many failures, shutting down.')
                    return self.early_shutdown()
            d['test_methods'].remove(result['method']['name'])
        else:
            # Fixture method
            if result['method']['name'] not in d['fixture_methods']:
                raise ValueError("Method %s not checked out by runner %s." % (result['method']['name'], runner_id))

            d['fixture_method_results'].append((result['method']['name'], result))
            d['fixture_methods'].remove(result['method']['name'])

        d['timeout_time'] = time.time() + self.runner_timeout

        if not d['test_methods'] and not d['fixture_methods']:
            self.check_in_class(runner_id, class_path, finished=True)

    def run(self):
        class TestsHandler(tornado.web.RequestHandler):
            @tornado.web.asynchronous
            def get(handler):
                runner_id = handler.get_argument('runner')

                if self.shutting_down:
                    self.runners_outstanding.discard(runner_id)
                    return handler.finish(json.dumps({
                        'finished': True,
                    }))

                if self.revision and self.revision != handler.get_argument('revision'):
                    return handler.send_error(409, reason="Incorrect revision %s -- server is running revision %s" % (handler.get_argument('revision'), self.revision))

                def callback(test_dict):
                    self.runners_outstanding.discard(runner_id)
                    handler.finish(json.dumps({
                        'class': test_dict['class_path'],
                        'test_methods': test_dict['test_methods'],
                        'finished': False,
                    }))

                def empty_callback():
                    self.runners_outstanding.discard(runner_id)
                    handler.finish(json.dumps({
                        'finished': True,
                    }))

                self.get_next_test(runner_id, callback, empty_callback)

            def finish(handler, *args, **kwargs):
                super(TestsHandler, handler).finish(*args, **kwargs)
                tornado.ioloop.IOLoop.instance().add_callback(handler.after_finish)

            def after_finish(handler):
                if self.shutting_down and not self.runners_outstanding:
                    iol = tornado.ioloop.IOLoop.instance()
                    iol.add_callback(iol.stop)

        class ResultsHandler(tornado.web.RequestHandler):
            def post(handler):
                runner_id = handler.get_argument('runner')
                self.runners_outstanding.add(runner_id)
                result = json.loads(handler.request.body)

                try:
                    self.report_result(runner_id, result)
                except ValueError, e:
                    return handler.send_error(409, reason=str(e))

                return handler.finish("kthx")

            def get_error_html(handler, status_code, **kwargs):
                reason = kwargs.pop('reason', None)
                if reason:
                    return reason
                else:
                    return super(ResultsHandler, handler).get_error_html(status_code, **kwargs)

        # Enqueue all of our tests.
        for test_instance in self.discover():
            class_path = '%s %s' % (test_instance.__module__, test_instance.__class__.__name__)

            fixtures = test_instance.class_setup_fixtures + \
                test_instance.class_teardown_fixtures + \
                test_instance.class_setup_teardown_fixtures * 2 + \
                [test_instance.classSetUp, test_instance.classTearDown]

            for fixture in fixtures:
                self.fixture_method_types[(class_path, fixture.__name__)] = fixture._fixture_type

            # Save the list of fixtures, in case we need to rerun this class later.
            self.fixtures_for_class[class_path] = tuple(fixture.__name__ for fixture in fixtures)

            test_dict = {
                'class_path': class_path,
                'test_methods': [test.__name__ for test in test_instance.runnable_test_methods()],
                'fixture_methods' : list(self.fixtures_for_class[class_path])
            }

            if test_dict['test_methods']:
                self.test_queue.put(0, test_dict)

        # Start an HTTP server.
        application = tornado.web.Application([
            (r"/tests", TestsHandler),
            (r"/results", ResultsHandler),
        ])

        server = tornado.httpserver.HTTPServer(application)
        server.listen(self.serve_port)

        def timeout_server():
            if time.time() > self.last_activity_time + self.server_timeout:
                logging.error('No client activity for %ss, shutting down.' % self.server_timeout)
                self.shutdown()
            else:
                tornado.ioloop.IOLoop.instance().add_timeout(self.last_activity_time + self.server_timeout, timeout_server)
        self.activity()
        timeout_server()  # Set the first callback.

        tornado.ioloop.IOLoop.instance().start()

        report = [reporter.report() for reporter in self.test_reporters]
        return all(report)

    def activity(self):
        self.last_activity_time = time.time()

    def check_out_class(self, runner, test_dict):
        self.activity()

        self.checked_out[test_dict['class_path']] = {
            'runner' : runner,
            'class_path' : test_dict['class_path'],
            'test_methods' : set(test_dict['test_methods']),
            # At some point this should maybe be a faster multiset implementation, but python 2.5/2.6 don't have a decent built-in implementation afaict.
            'fixture_methods' : test_dict['fixture_methods'],
            'fixture_method_results' : [],
            'failed_methods' : {},
            'passed_methods' : {},
            'start_time' : time.time(),
            'timeout_time' : time.time() + self.runner_timeout,
        }

        self.timeout_class(runner, test_dict['class_path'])

    def check_in_class(self, runner, class_path, timed_out=False, finished=False, early_shutdown=False):
        if not timed_out:
            self.activity()

        if 1 != len([opt for opt in (timed_out, finished, early_shutdown) if opt]):
            raise ValueError("Must set exactly one of timed_out, finished, or early_shutdown.")

        if class_path not in self.checked_out:
            raise ValueError("Class path %r not checked out." % class_path)
        if not early_shutdown and self.checked_out[class_path]['runner'] != runner:
            raise ValueError("Class path %r not checked out by runner %r." % (class_path, runner))

        d = self.checked_out.pop(class_path)

        # The set of class_setup_teardown fixtures we've reported already.
        seen_class_setup_teardowns = set()

        def report(result_dict):
            for reporter in self.test_reporters:
                if result_dict['method']['fixture_type'] == 'class_setup':
                    reporter.class_setup_start(result_dict)
                    reporter.class_setup_complete(result_dict)
                elif result_dict['method']['fixture_type'] == 'class_teardown':
                    reporter.class_teardown_start(result_dict)
                    reporter.class_teardown_complete(result_dict)
                elif result_dict['method']['fixture_type'] == 'class_setup_teardown':
                    # The first time we report a class_setup_teardown, it should be sent through class_setup_(start|complete)
                    if method not in seen_class_setup_teardowns:
                        reporter.class_setup_start(result_dict)
                        reporter.class_setup_complete(result_dict)
                        seen_class_setup_teardowns.add(method)
                    else:
                        reporter.class_teardown_start(result_dict)
                        reporter.class_teardown_complete(result_dict)
                else:
                    reporter.test_start(result_dict)
                    reporter.test_complete(result_dict)

        for method, result_dict in itertools.chain(
                    d['fixture_method_results'],
                    d['passed_methods'].iteritems(),
                    ((method, result) for (method, result) in d['failed_methods'].iteritems() if early_shutdown or (class_path, method) in self.failed_rerun_methods),
                ):
            result_dict['previous_run'] = self.previous_run_results.get((class_path, method), None)
            report(result_dict)

        #Requeue failed tests
        requeue_dict = {
            'last_runner' : runner,
            'class_path' : d['class_path'],
            'test_methods' : [],
            'fixture_methods' : list(self.fixtures_for_class[d['class_path']]),
        }

        for method, result_dict in d['failed_methods'].iteritems():
            if (class_path, method) not in self.failed_rerun_methods:
                requeue_dict['test_methods'].append(method)
                self.failed_rerun_methods.add((class_path, method))
                result_dict['previous_run'] = self.previous_run_results.get((class_path, method), None)
                self.previous_run_results[(class_path, method)] = result_dict

        if finished:
            if len(d['test_methods']) != 0:
                raise ValueError("check_in_class called with finished=True but this class (%s) still has %d methods without results." % (class_path, len(d['test_methods'])))
        elif timed_out:
            # Requeue or report timed-out tests.

            for method in list(d['test_methods']) + d['fixture_methods']:
                # Fake the results dict.
                error_message = "The runner running this method (%s) didn't respond within %ss.\n" % (runner, self.runner_timeout)
                module, _, classname = class_path.partition(' ')

                result_dict = {
                    'previous_run' : self.previous_run_results.get((class_path, method), None),
                    'start_time' : time.time() - self.runner_timeout,
                    'end_time' : time.time(),
                    'run_time' : self.runner_timeout,
                    'normalized_run_time' : "%.2fs" % (self.runner_timeout),
                    'complete': True,  # We've tried running the test.
                    'success' : False,
                    'failure' : False,
                    'error' : True,
                    'interrupted' : False,
                    'exception_info' : [error_message],
                    'exception_info_pretty' : [error_message],
                    'runner_id' : runner,
                    'method' : {
                        'module' : module,
                        'class' : classname,
                        'name' : method,
                        'full_name' : "%s.%s" % (class_path, method),
                        'fixture_type' : self.fixture_method_types.get((class_path, method)),
                    }
                }

                if not self.fixture_method_types.get((class_path, method)) and (class_path, method) not in self.timeout_rerun_methods:
                    requeue_dict['test_methods'].append(method)
                    self.timeout_rerun_methods.add((class_path, method))
                    self.previous_run_results[(class_path, method)] = result_dict
                else:
                    report(result_dict)

        if requeue_dict['test_methods']:
            self.test_queue.put(-1, requeue_dict)

        if self.test_queue.empty() and len(self.checked_out) == 0:
            self.shutdown()

    def timeout_class(self, runner, class_path):
        """Check that it's actually time to rerun this class; if not, reset the timeout. Check the class in and rerun it."""
        d = self.checked_out.get(class_path, None)

        if not d:
            return

        if time.time() < d['timeout_time']:
            # We're being called for the first time, or someone has updated timeout_time since the timeout was set (e.g. results came in)
            tornado.ioloop.IOLoop.instance().add_timeout(d['timeout_time'], lambda: self.timeout_class(runner, class_path))
            return

        try:
            self.check_in_class(runner, class_path, timed_out=True)
        except ValueError:
            # If another builder has checked out the same class in the mean time, don't throw an error.
            pass

    def early_shutdown(self):
        for class_path in self.checked_out.keys():
            self.check_in_class(None, class_path, early_shutdown=True)
        self.shutdown()

    def shutdown(self):
        if self.shutting_down:
            # Try not to shut down twice.
            return

        self.shutting_down = True
        self.test_queue.finalize()
        iol = tornado.ioloop.IOLoop.instance()
        # Can't immediately call stop, otherwise the runner currently POSTing its results will get a Connection Refused when it tries to ask for the next test.

        if self.runners_outstanding:
            # Stop in 5 seconds if all the runners_outstanding don't come back by then.
            iol.add_timeout(time.time() + self.shutdown_delay_for_outstanding_runners, iol.stop)
        else:
            # Give tornado enough time to finish writing to all the clients, then shut down.
            iol.add_timeout(time.time() + self.shutdown_delay_for_connection_close, iol.stop)
