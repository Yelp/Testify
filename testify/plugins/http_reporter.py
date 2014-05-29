import httplib
import logging
import Queue
import threading
import urllib2
import time

from testify import test_reporter

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json

class HTTPReporter(test_reporter.TestReporter):
    def report_results(self):
        while True:
            result_set = self.result_queue.get()
            my_url = 'http://%s/results?runner=%s' % (self.connect_addr, self.runner_id), json.dumps(result_set)
            print ' tttttt runner->',self.runner_id, ' url->',my_url
            for result in result_set:
                result['runner_id'] = self.runner_id

            try:
                try:
                    urllib2.urlopen('http://%s/results?runner=%s' % (self.connect_addr, self.runner_id), json.dumps(result_set))
                    logging.warning('t -> %s--------- res-> %s' % (str(time.time()),str(result_set)))
                except (urllib2.URLError, httplib.BadStatusLine), e:
                    # Retry once.
                    urllib2.urlopen('http://%s/results?runner=%s' % (self.connect_addr, self.runner_id), json.dumps(result_set))
                    logging.warning('t-> %s --------- RR res-> %s' % (str(time.time()), str(result_set)))
            except urllib2.HTTPError, e:
                logging.error('Skipping returning results for test %s because of error: %s' % (result_set[0]['method']['full_name'], e.read()))
            except Exception, e:
                logging.error('Skipping returning results for test %s because of unknown error: %s' % (result_set[0]['method']['full_name'], e))

            self.result_queue.task_done()


    def __init__(self, options, connect_addr, runner_id, *args, **kwargs):
        self.connect_addr = connect_addr
        self.runner_id = runner_id

        self.result_queue = Queue.Queue()
        self.results_dict = {}
        self.reporting_thread = threading.Thread(target=self.report_results)
        # A daemon thread should be fine, since the test_runner_client won't quit until the server goes away or says to quit.
        # In either of these cases, any outstanding results won't be processed anyway, so there's no reason for us to wait
        # for the reporting thread to finish before quitting.
        self.reporting_thread.daemon = True
        self.reporting_thread.start()

        super(HTTPReporter, self).__init__(options, *args, **kwargs)

    def test_case_complete(self, result):
        """Add a result to result_queue. The result is specially constructed to
        signal to the test_runner server that a test_runner client has finished
        running an entire TestCase.
        """
        full_name = result['method']['module'] + '.' + result['method']['class']
        print ' ---- in test_CASE_complete full_name->',full_name
        if full_name not in self.results_dict.keys():
            print ' !!!!!!! ERROR: something weird is going on'
        self.results_dict[full_name].append(result)
        #self.result_queue.put(result)
        print '------- in test_CASE_complete class->',full_name,' done res->',self.results_dict[full_name]
        self.result_queue.put(self.results_dict[full_name])

    def class_teardown_complete(self, result):
        """If there was an error during class_teardown, insert the result
        containing the error into the queue that report_results pulls from.
        """
        if not result['success']:
            self.result_queue.put(result)

    def test_complete(self, result):
        #self.result_queue.put(result)
        full_name = result['method']['module'] + '.' + result['method']['class']
        print ' ---- in test_complete full_name->',full_name
        if full_name not in self.results_dict.keys():
            self.results_dict[full_name] = []

        self.results_dict[full_name].append(result)

    def report(self):
        """Wait until all results have been sent back."""
        self.result_queue.join()
        return True


def build_test_reporters(options):
    if options.connect_addr:
        return [HTTPReporter(options, options.connect_addr, options.runner_id)]
    return []

# vim: set ts=4 sts=4 sw=4 et:
