from testify import test_reporter
import urllib2
import httplib
import logging

try:
	import simplejson as json
	_hush_pyflakes = [json]
	del _hush_pyflakes
except ImportError:
	import json

class HTTPReporter(test_reporter.TestReporter):
	def __init__(self, options, *args, **kwargs):
		self.connect_addr = options.connect_addr
		self.runner_id = options.runner_id

		super(HTTPReporter, self).__init__(options, *args, **kwargs)

	def test_complete(self, result):
		result['runner_id'] = self.runner_id
		try:
			try:
				urllib2.urlopen('http://%s/results?runner=%s' % (self.connect_addr, self.runner_id), json.dumps(result))
			except (urllib2.URLError, httplib.BadStatusLine), e:
				# Retry once.
				urllib2.urlopen('http://%s/results?runner=%s' % (self.connect_addr, self.runner_id), json.dumps(result))
		except urllib2.HTTPError, e:
			logging.error('Skipping returning results for test %s because of error: %s' % (result['method']['full_name'], e.read()))


def build_test_reporters(options):
	if options.connect_addr:
		return [HTTPReporter(options)]
	return []
