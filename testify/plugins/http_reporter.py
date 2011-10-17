from testify import test_reporter
import urllib2
import time

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json

class HTTPReporter(test_reporter.TestReporter):
	def __init__(self, options, *args, **kwargs):
		self.connect_addr = options.connect_addr
		super(HTTPReporter, self).__init__(options, *args, **kwargs)

	def test_complete(self, test_case, result):
		if test_case.is_fixture_method(result.test_method) or test_case.method_excluded(result.test_method):
			return
		urllib2.urlopen('http://%s/results?runner=test' % self.connect_addr, json.dumps({
			'class' : '%s %s' % (result.test_method.im_class.__module__, result.test_method.im_class.__name__),
			'method' : result.test_method.__name__,
			'success' : bool(result.success),
			'start_time' : time.mktime(result.start_time.timetuple()),
			'end_time' : time.mktime(result.end_time.timetuple()),
            'tb' : exception.format_exception_info(result.exception_info) if not result.success else None,
            'error' : str(out_result['tb'][-1]).strip() if not result.success else None,
		}))


def build_test_reporters(options):
	if options.connect_addr:
		return [HTTPReporter(options)]
	return []