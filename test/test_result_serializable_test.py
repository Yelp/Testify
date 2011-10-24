from testify import test_case
from testify import run
from testify import test_result

try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json

class TestResultIsSerializableTestCase(test_case.TestCase):
	class NullTestCase(test_case.TestCase):
		def test_method(self):
			return

	null_test_case = NullTestCase()

	def test_test_result_is_serializable(self):
		result = test_result.TestResult(self.null_test_case.test_method)
		json.dumps(result.to_dict())
		result.start()
		json.dumps(result.to_dict())
		result.end_in_success()
		json.dumps(result.to_dict())

if __name__ == '__main__':
    run()