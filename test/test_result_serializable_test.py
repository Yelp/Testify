import json

from testify import test_case
from testify import run
from testify import test_result
from testify import assert_equal


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

    def test_not_garbled_by_serialization(self):
        """Make sure that converting to JSON and back results in the same dictionary."""
        result = test_result.TestResult(self.null_test_case.test_method)
        assert_equal(
            result.to_dict(),
            json.loads(json.dumps(result.to_dict()))
        )

        result.start()
        assert_equal(
            result.to_dict(),
            json.loads(json.dumps(result.to_dict()))
        )

        result.end_in_success()
        assert_equal(
            result.to_dict(),
            json.loads(json.dumps(result.to_dict()))
        )


if __name__ == '__main__':
    run()
