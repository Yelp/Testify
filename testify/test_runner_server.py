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

class TestRunnerServer(TestRunner):
    RUNNER_TIMEOUT = 300

    def __init__(self, *args, **kwargs):
        self.serve_port = kwargs.pop('serve_port')

        self.test_queue = Queue.PriorityQueue()
        self.checked_out = {}

        super(TestRunnerServer, self).__init__(*args, **kwargs)

    def run(self):
        class TestsHandler(tornado.web.RequestHandler):
            def get(handler):
                runner_id = handler.get_argument('runner')
                if not self.test_queue.empty():
                    methods = None
                    _, tests_dict = self.test_queue.get()

                    test_case_class = tests_dict['class']
                    test_instance = test_case_class(
                        suites_include=self.suites_include,
                        suites_exclude=self.suites_exclude,
                        suites_require=self.suites_require)


                    class_path = '%s %s' % (test_case_class.__module__, test_case_class.__name__)
                    methods = [test.__name__ for test in test_instance.runnable_test_methods()]

                    # If this test class has no methods, skip it.
                    if not methods:
                        return handler.get()

                    self.check_out_class(runner_id, class_path, methods)

                    handler.write(json.dumps({
                        'class': class_path,
                        'methods': methods,
                        'finished': False,
                    }))
                else:
                    handler.write(json.dumps({
                        'finished': True,
                    }))

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
            self.test_queue.put((0, test_dict))

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

    def check_out_class(self, runner, class_path, methods, timeout_rerun=False, failed_rerun=False):
        self.checked_out[class_path] = {
            'runner' : runner,
            'class_path' : class_path,
            'methods' : set(methods),
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
                iol = tornado.ioloop.IOLoop.instance()
                iol.add_timeout(time.time()+1, iol.stop)
