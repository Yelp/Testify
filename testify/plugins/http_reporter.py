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
        ended = False
        while True:
            result_batch = []
            while time.time() - self.batch_timer < self.BATCH_FREQ or len(result_batch)==0:
                print '    t->',time.time(),'    -> calling get on queue'
                try:
                    result_case = self.result_queue.get_nowait()
                    if result_case =='finished':
                        print '--------------- t->',time.time(),' got a finish --------'
                        ended = True
                        break
                    else:
                        print ' ------- t->',time.time(),'vvvv got some task vvvvvv'
                        result_batch.append(result_case)
                except Queue.Empty:
                    print '---- t->',time.time(),' q empty .. sleep for a sec'
                    time.sleep(1)
            if ended == True:
                print ' EVERYTHING FINISHED t->',time.time()
                break

            print ' TIME->',time.time(),' runner->',self.runner_id, ' sending batch of size->',len(result_batch)
            for result_case in result_batch:
                for result in result_case:
                    result['runner_id'] = self.runner_id

            try:
                try:
                    urllib2.urlopen('http://%s/results?runner=%s' % (self.connect_addr, self.runner_id), json.dumps(result_batch))
                    logging.warning('t -> %s--------- res-> %s' % (str(time.time()),str(result_batch)))
                    self.batch_timer = time.time()
                except (urllib2.URLError, httplib.BadStatusLine), e:
                    # Retry once.
                    urllib2.urlopen('http://%s/results?runner=%s' % (self.connect_addr, self.runner_id), json.dumps(result_batch))
                    self.batch_timer = time.time()
                    logging.warning('t-> %s --------- RR res-> %s' % (str(time.time()), str(result_batch)))
            except urllib2.HTTPError, e:
                logging.error('Skipping returning results for current batch because of error: %s' % (e.read()))
            except Exception, e:
                logging.error('Skipping returning results for current batch because of unknown error: %s' % (e))

            self.result_queue.task_done()
        
        print '      -> t->',time.time(),' QUITTING ---------'


    def __init__(self, options, connect_addr, runner_id, *args, **kwargs):
        self.connect_addr = connect_addr
        self.runner_id = runner_id
        self.BATCH_FREQ = 5
        self.batch_timer = time.time()
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
        print ' ---- t->',time.time(),' in test_CASE_complete full_name->',full_name
        if full_name not in self.results_dict.keys():
            print ' !!!!!!! ERROR: something weird is going on'
        self.results_dict[full_name].append(result)
        #self.result_queue.put(result)
        print '------- t->',time.time(),'  in test_CASE_complete class->',full_name,' done res->',self.results_dict[full_name]
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
        print ' ---- t->',time.time(),' in test_complete full_name->',full_name
        if full_name not in self.results_dict.keys():
            self.results_dict[full_name] = []

        self.results_dict[full_name].append(result)

    def add_finished(self):
        print '+++++++++++++++++++++++++ called at the end +++++++++++++++++'
        self.result_queue.put('finished')
        print '++++++++++++++++ pushed finished +++++++'
    

    def report(self):
        """Wait until all results have been sent back."""
#        self.add_finished()
        print '======== called join ======='
        #self.result_queue.join()
        return True


def build_test_reporters(options):
    if options.connect_addr:
        return [HTTPReporter(options, options.connect_addr, options.runner_id)]
    return []

# vim: set ts=4 sts=4 sw=4 et:
