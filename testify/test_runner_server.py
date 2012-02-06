"""
Client-server setup to evenly distribute tests across multiple processes. The server
discovers all test classes and enqueues them, then clients connect to the server,
receive tests to run, and send back their results.

The server keeps track of the overall status of the run and manages timeouts and retries.
"""

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


class AsyncQueue(object):
    def __init__(self):
        self.data_queue = Queue.PriorityQueue()
        self.callback_queue = Queue.PriorityQueue()
        self.finalized = False

    def get(self, c_priority, callback):
        if self.finalized:
            callback(None, None)
            return
        try:
            d_priority, data = self.data_queue.get_nowait()
            callback(d_priority, data)
        except Queue.Empty:
            self.callback_queue.put((c_priority, callback,))

    def put(self, d_priority, data):
        try:
            c_priority, callback = self.callback_queue.get_nowait()
            callback(d_priority, data)
        except Queue.Empty:
            self.data_queue.put((d_priority, data,))

    def empty(self):
        return self.data_queue.empty()

    def waiting(self):
        return not self.callback_queue.empty()

    def finalize(self):
        """Call all queued callbacks with None, and make sure any future calls to get() immediately call their callback with None."""
        self.finalized = True
        try:
            while True:
                _, callback = self.callback_queue.get_nowait()
                callback(None, None)
        except Queue.Empty:
            pass

class TestRunnerServer(TestRunner):
    def __init__(self, *args, **kwargs):
        self.serve_port = kwargs.pop('serve_port')
        self.runner_timeout = kwargs['options'].runner_timeout
        self.revision = kwargs['options'].revision
        self.server_timeout = kwargs['options'].server_timeout

        self.test_queue = AsyncQueue()
        self.checked_out = {} # Keyed on class path (module class).
        self.failed_rerun_methods = {} # Keyed on tuple (class_path, method), values are results dicts.
        self.timeout_rerun_methods = set() # The set of all (class_path, method) that have timed out once.

        self.runners = set() # The set of runner_ids who have asked for tests.

        super(TestRunnerServer, self).__init__(*args, **kwargs)

    def run(self):
        class TestsHandler(tornado.web.RequestHandler):
            @tornado.web.asynchronous
            def get(handler):
                runner_id = handler.get_argument('runner')
                if self.revision and self.revision != handler.get_argument('revision'):
                    return handler.send_error(409, reason="Incorrect revision %s -- server is running revision %s" % (handler.get_argument('revision'), self.revision))

                self.runners.add(runner_id)

                def callback(priority, test_dict):
                    if test_dict:
                        if test_dict.get('last_runner', None) != runner_id or (self.test_queue.empty() and len(self.runners) <= 1):
                            self.check_out_class(runner_id, test_dict)

                            handler.finish(json.dumps({
                                'class': test_dict['class_path'],
                                'methods': test_dict['methods'],
                                'finished': False,
                            }))
                        else:
                            if self.test_queue.empty():
                                # Put the test back in the queue, and queue ourselves to pick up the next test queued.
                                self.test_queue.put(priority, test_dict)
                                self.test_queue.callback_queue.put((-1, callback))
                            else:
                                # Get the next test, process it, then place the old test back in the queue.
                                self.test_queue.get(0, callback)
                                self.test_queue.put(priority, test_dict)
                    else:
                        handler.finish(json.dumps({
                            'finished': True,
                        }))

                self.test_queue.get(0, callback)

        class ResultsHandler(tornado.web.RequestHandler):
            def post(handler):
                runner_id = handler.get_argument('runner')
                result = json.loads(handler.request.body)

                class_path = '%s %s' % (result['method']['module'], result['method']['class'])
                d = self.checked_out.get(class_path)

                if not d:
                    return handler.send_error(409, reason="Class %s not checked out." % class_path)
                if d['runner'] != runner_id:
                    return handler.send_error(409, reason="Class %s checked out by runner %s, not %s" % (class_path, d['runner'], runner_id))
                if result['method']['name'] not in d['methods']:
                    return handler.send_error(409, reason="Method %s not checked out by runner %s." % (result['method']['name'], runner_id))

                if result['success']:
                    d['passed_methods'][result['method']['name']] = result
                else:
                    d['failed_methods'][result['method']['name']] = result
                    self.failure_count += 1
                    if self.failure_limit and self.failure_count >= self.failure_limit:
                        logging.error('Too many failures, shutting down.')
                        self.early_shutdown()
                        return handler.finish("Too many failures, shutting down.")

                d['timeout_time'] = time.time() + self.runner_timeout

                d['methods'].remove(result['method']['name'])

                if not d['methods']:
                    self.check_in_class(runner_id, class_path, finished=True)

                return handler.finish("kthx")

            def get_error_html(handler, status_code, **kwargs):
                reason = kwargs.pop('reason', None)
                if reason:
                    return reason
                else:
                    return super(ResultsHandler, handler).get_error_html(status_code, **kwargs)

        # Enqueue all of our tests.
        for test_instance in self.discover():
            test_dict = {
                'class_path' : '%s %s' % (test_instance.__module__, test_instance.__class__.__name__),
                'methods' : [test.__name__ for test in test_instance.runnable_test_methods()],
            }

            if test_dict['methods']:
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
        timeout_server() # Set the first callback.

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
            'methods' : set(test_dict['methods']),
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

        for method, result_dict in itertools.chain(
                    d['passed_methods'].iteritems(),
                    ((method, result) for (method, result) in d['failed_methods'].iteritems() if early_shutdown or (class_path, method) in self.failed_rerun_methods),
                ):
            for reporter in self.test_reporters:
                result_dict['previous_run'] = self.failed_rerun_methods.get((class_path, method), None)
                reporter.test_start(result_dict)
                reporter.test_complete(result_dict)

        #Requeue failed tests
        requeue_dict = {
            'last_runner' : runner,
            'class_path' : d['class_path'],
            'methods' : [],
        }

        for method, result_dict in d['failed_methods'].iteritems():
            if (class_path, method) not in self.failed_rerun_methods:
                requeue_dict['methods'].append(method)
                self.failed_rerun_methods[(class_path, method)] = result_dict

        if finished:
            if len(d['methods']) != 0:
                raise ValueError("check_in_class called with finished=True but this class (%s) still has %d methods without results." % (class_path, len(d['methods'])))
        elif timed_out:
            # Requeue timed-out tests.
            for method in d['methods']:
                if (class_path, method) not in self.timeout_rerun_methods:
                    requeue_dict['methods'].append(method)
                    self.timeout_rerun_methods.add((class_path, method))
                else:
                    error_message = "The runner running this method (%s) didn't respond within %ss." % (runner, self.runner_timeout)
                    module, _, classname = class_path.partition(' ')

                    # Fake the results dict.
                    result_dict = {
                        'previous_run' : None,
                        'start_time' : time.time()-self.runner_timeout,
                        'end_time' : time.time(),
                        'run_time' : self.runner_timeout,
                        'normalized_run_time' : "%.2fs" % (self.runner_timeout),
                        'complete': True, # We've tried running the test.
                        'success' : False,
                        'failure' : False,
                        'error' : True,
                        'interrupted' : False,
                        'exception_info' : error_message,
                        'exception_info_pretty' : error_message,
                        'runner_id' : runner,
                        'method' : {
                            'module' : module,
                            'class' : classname,
                            'name' : method,
                            'full_name' : "%s.%s" % (class_path, method),
                            'fixture_type' : None,
                        }
                    }

                    for reporter in self.test_reporters:
                        reporter.test_start(result_dict)
                        reporter.test_complete(result_dict)


        if requeue_dict['methods']:
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

        self.check_in_class(runner, class_path, timed_out=True)

    def early_shutdown(self):
        for class_path in self.checked_out.keys():
            self.check_in_class(None, class_path, early_shutdown=True)
        self.shutdown()

    def shutdown(self):
        # Can't immediately call stop, otherwise the current POST won't ever get a response.
        self.test_queue.finalize()
        iol = tornado.ioloop.IOLoop.instance()
        iol.add_timeout(time.time()+1, iol.stop)

