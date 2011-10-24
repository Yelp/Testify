from testify import test_reporter
import urllib2
import time
from testify.utils import exception

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

	def test_complete(self, result):
		try:
			urllib2.urlopen('http://%s/results?runner=test' % self.connect_addr, json.dumps(result))
		except urllib2.URLError:
			#TODO log the error.
			pass


def build_test_reporters(options):
	if options.connect_addr:
		return [HTTPReporter(options)]
	return []