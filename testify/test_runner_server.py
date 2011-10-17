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

test_queue = Queue.PriorityQueue()
checked_out = {}

class TestRunnerServer(TestRunner):
    def __init__(self, *args, **kwargs):
        self.serve_port = kwargs.pop('serve_port')
        super(TestRunnerServer, self).__init__(*args, **kwargs)

    def run(self):
        class TestsHandler(tornado.web.RequestHandler):
            def get(handler):
                runner_id = handler.get_argument('runner')
                if not test_queue.empty():
                    _, tests_dict = test_queue.get(block=False)
                    checked_out[tests_dict['class']] = tests_dict

                    test_list = []

                    test_case_class = tests_dict['class']
                    test_instance = test_case_class(
                        suites_include=self.suites_include,
                        suites_exclude=self.suites_exclude,
                        suites_require=self.suites_require)

                    handler.write(json.dumps({
                        'class': '%s %s' % (test_case_class.__module__, test_case_class.__name__),
                        'methods': [test.__name__ for test in test_instance.runnable_test_methods()],
                        'finished': False,
                    }))
                else:
                    handler.write(json.dumps({
                        'finished': True,
                    }))

        class ResultsHandler(tornado.web.RequestHandler):
            def post(handler):
                runner_id = handler.get_argument('runner')
                results = json.loads(handler.request.body)
                checked_out[results['class']] = None
                handler.write("kthx")


        # Enqueue all of our tests.
        for test_dict in self.discover():
            test_queue.put((0, test_dict))

        # Start an HTTP server.
        application = tornado.web.Application([
            (r"/tests", TestsHandler),
            (r"/results", ResultsHandler),
        ])

        server = tornado.httpserver.HTTPServer(application)
        server.listen(self.serve_port)
        tornado.ioloop.IOLoop.instance().start()
