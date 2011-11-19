from test_runner import TestRunner
import urllib2
try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json
import time
import logging

class TestRunnerClient(TestRunner):
    def __init__(self, *args, **kwargs):
        self.connect_addr = kwargs.pop('connect_addr')
        self.runner_id = kwargs.pop('runner_id')
        super(TestRunnerClient, self).__init__(*args, **kwargs)

    def discover(self):
        finished = False
        first_connect = True
        while not finished:
            class_path, methods, finished = self.get_next_tests(retry_limit=(60 if first_connect else 1))
            first_connect = False
            if class_path and methods:
                module_path, _, class_name = class_path.partition(' ')

                module = __import__(module_path)
                for part in module_path.split('.')[1:]:
                    try:
                        module = getattr(module, part)
                    except AttributeError:
                        logging.error("discovery(%s) failed: module %s has no attribute %r" % (module_path, module, part))

                klass = getattr(module, class_name)
                yield klass(name_overrides=methods)

    def get_next_tests(self, retry_delay=10, retry_limit=0):
        try:
            response = urllib2.urlopen('http://%s/tests?runner=%s' % (self.connect_addr, self.runner_id))
            d = json.load(response)
            return (d.get('class'), d.get('methods'), d['finished'])
        except urllib2.URLError, e:
            if retry_limit > 0:
                logging.warning("Got error %r when requesting tests, retrying %d more times." % (e, retry_limit))
                time.sleep(retry_delay)
                return self.get_next_tests(retry_limit=retry_limit-1)
            else:
                return None, None, True # Stop trying if we can't connect to the server.
