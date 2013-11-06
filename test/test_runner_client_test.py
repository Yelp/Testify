import testify

from testify.test_runner_client import TestRunnerClient


class ClientDiscoveryTestCase(testify.TestCase):
    """Integration tests for TestRunnerClient's test discovery."""

    @testify.class_setup
    def init_test_runner_client(self):
        self.client = TestRunnerClient(
                None,
                connect_addr=None,
                runner_id=None,
                options=testify.turtle.Turtle(),
        )

    def discover(self, class_path):
        def foo(*args, **kwargs):
            return class_path, 'test_foo', True

        self.client.get_next_tests = foo
        return [x for x in self.client.discover()]

    def test_discover_testify_case(self):
        assert self.discover('test.test_suite_subdir.define_testcase DummyTestCase')

    def test_discover_unittest_case(self):
        assert self.discover('test.test_suite_subdir.define_unittestcase TestifiedDummyUnitTestCase')
