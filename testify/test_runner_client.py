"""
Client-server setup for evenly distributing tests across multiple processes.
See the test_runner_server module.
"""
import urllib2
try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json
import time
import logging

import test_discovery
from test_runner import TestRunner


class TestRunnerClient(TestRunner):
    def __init__(self, *args, **kwargs):
        self.connect_addr = kwargs.pop('connect_addr')
        self.runner_id = kwargs.pop('runner_id')
        self.revision = kwargs['options'].revision

        self.retry_limit = kwargs['options'].retry_limit
        self.retry_interval = kwargs['options'].retry_interval
        self.retry_backoff = kwargs['options'].retry_backoff
        self.reconnect_retry_limit = kwargs['options'].reconnect_retry_limit

        super(TestRunnerClient, self).__init__(*args, **kwargs)

    def discover(self):
        finished = False
        first_connect = True
        while not finished:
            class_path, methods, finished = self.get_next_tests(
                retry_limit=(self.retry_limit if first_connect else self.reconnect_retry_limit),
                retry_interval=self.retry_interval,
            )
            first_connect = False
            if class_path and methods:
                module_path, _, class_name = class_path.partition(' ')

                klass = test_discovery.import_test_class(module_path, class_name)
                yield klass(name_overrides=methods)

    def get_next_tests(self, retry_interval, retry_limit):
        try:
            if self.revision:
                url = 'http://%s/tests?runner=%s&revision=%s' % (self.connect_addr, self.runner_id, self.revision)
            else:
                url = 'http://%s/tests?runner=%s' % (self.connect_addr, self.runner_id)
            response = urllib2.urlopen(url)
            d = json.load(response)
            return (d.get('class'), d.get('methods'), d['finished'])
        except urllib2.HTTPError, e:
            logging.warning("Got HTTP status %d when requesting tests -- bailing" % (e.code))
            return None, None, True
        except urllib2.URLError, e:
            if retry_limit > 0:
                logging.warning("Got error %r when requesting tests, retrying in %g seconds (giving up in %g seconds)...", e, retry_interval, retry_limit)
                time.sleep(min(retry_interval, retry_limit))
                return self.get_next_tests(retry_limit=retry_limit-retry_interval, retry_interval=retry_interval+self.retry_backoff)
            else:
                return None, None, True # Stop trying if we can't connect to the server.
