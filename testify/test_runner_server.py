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

import Queue
import time
import itertools
import time

class AsyncQueue(object):
    def __init__(self):
        self.data_queue = Queue.PriorityQueue()
        self.callback_queue = Queue.PriorityQueue()
        self.finalized = False

    def get(self, priority, callback):
        if self.finalized:
            callback(None)
            return
        try:
            _, data = self.data_queue.get_nowait()
            callback(data)
        except Queue.Empty:
            self.callback_queue.put((priority, callback,))

    def put(self, priority, data):
        try:
            _, callback = self.callback_queue.get_nowait()
            callback(data)
        except Queue.Empty:
            self.data_queue.put((priority, data,))

    def empty(self):
        return self.data_queue.empty()

    def waiting(self):
        return self.callback_queue.empty()

    def finalize(self):
        self.finalized = True
        try:
            while True:
                _, callback = self.callback_queue.get_nowait()
                callback(None)
        except Queue.Empty:
            pass

class TestRunnerServer(TestRunner):
    RUNNER_TIMEOUT = 300

    def __init__(self, *args, **kwargs):
        self.serve_port = kwargs.pop('serve_port')

        self.test_queue = AsyncQueue()
        self.checked_out = {}

        super(TestRunnerServer, self).__init__(*args, **kwargs)

    def run(self):
        class TestsHandler(tornado.web.RequestHandler):
            @tornado.web.asynchronous
            def get(handler):
                runner_id = handler.get_argument('runner')

                def callback(test_dict):
                    if test_dict:
                        test_case_class = test_dict['class']
                        test_instance = test_case_class(
                            suites_include=self.suites_include,
                            suites_exclude=self.suites_exclude,
                            suites_require=self.suites_require)


                        self.check_out_class(runner_id, test_dict)

                        handler.finish(json.dumps({
                            'class': test_dict['class_path'],
                            'methods': test_dict['methods'],
                            'finished': False,
                        }))
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

                if not d or d['runner'] != runner_id:
                    return handler.send_error(409)

                handler.finish("kthx")
                handler.flush()

                if result['success']:
                    d['passed_methods'][result['method']['name']] = result
                else:
                    d['failed_methods'][result['method']['name']] = result

                d['timeout_time'] = time.time() + self.RUNNER_TIMEOUT

                d['methods'].remove(result['method']['name'])
                if not d['methods']:
                    self.check_in_class(runner_id, class_path, finished=True)


        # Enqueue all of our tests.
        for test_dict in self.discover():
            test_case_class = test_dict['class']
            test_instance = test_case_class(
                suites_include=self.suites_include,
                suites_exclude=self.suites_exclude,
                suites_require=self.suites_require)

            test_dict['class_path'] = '%s %s' % (test_case_class.__module__, test_case_class.__name__)
            test_dict['methods'] = [test.__name__ for test in test_instance.runnable_test_methods()]

            if test_dict['methods']:
                self.test_queue.put(0, test_dict)

        # Start an HTTP server.
        application = tornado.web.Application([
            (r"/tests", TestsHandler),
            (r"/results", ResultsHandler),
        ])

        server = tornado.httpserver.HTTPServer(application)
        server.listen(self.serve_port)
        tornado.ioloop.IOLoop.instance().start()

        report = [reporter.report() for reporter in self.test_reporters]
        return all(report)

    def check_out_class(self, runner, test_dict, timeout_rerun=False, failed_rerun=False):
        self.checked_out[test_dict['class_path']] = {
            'runner' : runner,
            'class_path' : test_dict['class_path'],
            'methods' : set(test_dict['methods']),
            'failed_methods' : {},
            'passed_methods' : {},
            'failed_rerun' : failed_rerun,
            'timeout_rerun' : timeout_rerun,
            'timeout_time' : time.time() + self.RUNNER_TIMEOUT,
        }

    def check_in_class(self, runner, class_path, timed_out=False, finished=False):
        if not timed_out and not finished:
            raise ValueError("Must set either timed_out or finished")

        if finished:
            if class_path not in self.checked_out:
                raise ValueError("Class path %r not checked out." % class_path)
            if self.checked_out[class_path]['runner'] != runner:
                raise ValueError("Class path %r not checked out by runner %r." % (class_path, runner))

            d = self.checked_out.pop(class_path)

            for result_dict in itertools.chain(d['passed_methods'].itervalues(), d['failed_methods'].itervalues()):
                for reporter in self.test_reporters:
                    reporter.test_start(result_dict)
                    reporter.test_complete(result_dict)

            if self.test_queue.empty() and len(self.checked_out) == 0:
                # Can't immediately call stop, otherwise the current POST won't ever get a response.
                self.test_queue.finalize()
                iol = tornado.ioloop.IOLoop.instance()
                iol.add_timeout(time.time()+1, iol.stop)
