import threading
import tornado.ioloop
import tornado.httpserver
import tornado.web
import Queue

from test.test_logger_test import ExceptionInClassFixtureSampleTests
from testify import assert_equal, setup_teardown, TestCase
from testify.test_runner import TestRunner
from testify.plugins.http_reporter import HTTPReporter

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json


class DummyTestCase(TestCase):
    __test__ = False
    def test(self):
        pass


class HTTPReporterTestCase(TestCase):
    @setup_teardown
    def make_fake_server(self):
        self.results_reported = []
        self.status_codes = Queue.Queue()

        class ResultsHandler(tornado.web.RequestHandler):
            def post(handler):
                result = json.loads(handler.request.body)
                self.results_reported.append(result)

                try:
                    status_code = self.status_codes.get_nowait()
                    handler.send_error(status_code)
                except Queue.Empty:
                    handler.finish("kthx")

            def get_error_html(handler, status, **kwargs    ):
                return "error"

        app = tornado.web.Application([(r"/results", ResultsHandler)])
        srv = tornado.httpserver.HTTPServer(app)
        srv.listen(0)
        portnum = self.get_port_number(srv)

        iol = tornado.ioloop.IOLoop.instance()
        thread = threading.Thread(target=iol.start)
        thread.daemon = True # If for some reason this thread gets blocked, don't prevent quitting.
        thread.start()

        self.connect_addr = "localhost:%d" % portnum

        yield

        iol.stop()
        thread.join()

    def get_port_number(self, server):
        if hasattr(server, "_sockets"): # tornado > 2.0
            _socket = server._sockets.values()[0]
        else: # tornado 1.2 or earlier
            _socket = server._socket
        return _socket.getsockname()[1]

    def test_http_reporter_reports(self):
        """A simple test to make sure the HTTPReporter actually reports things."""

        runner = TestRunner(DummyTestCase, test_reporters=[HTTPReporter(None, self.connect_addr, 'runner1')])
        runner.run()

        (method_result, test_case_result) = self.results_reported
        assert_equal(method_result['runner_id'], 'runner1')
        assert_equal(method_result['method']['class'], 'DummyTestCase')
        assert_equal(method_result['method']['name'], 'test')

    def test_http_reporter_tries_twice(self):
        self.status_codes.put(409)
        self.status_codes.put(409)

        runner = TestRunner(DummyTestCase, test_reporters=[HTTPReporter(None, self.connect_addr, 'tries_twice')])
        runner.run()

        (first, second, test_case_result) = self.results_reported

        assert_equal(first['runner_id'], 'tries_twice')
        assert_equal(first, second)

    def test_http_reporter_completed_test_case(self):
        runner = TestRunner(DummyTestCase, test_reporters=[HTTPReporter(None, self.connect_addr, 'runner1')])
        runner.run()

        (test_method_result, test_case_result) = self.results_reported
        assert_equal(test_case_result['method']['name'], 'run')

    def test_http_reporter_class_teardown_exception(self):
        runner = TestRunner(ExceptionInClassFixtureSampleTests.FakeClassTeardownTestCase, test_reporters=[HTTPReporter(None, self.connect_addr, 'runner1')])
        runner.run()

        (test1_method_result, test2_method_result, class_teardown_result, test_case_result) = self.results_reported
        assert_equal(test_case_result['method']['name'], 'run')


# vim: set ts=4 sts=4 sw=4 et:
