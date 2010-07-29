from testify import test_case

class DummyTestCase(test_case.TestCase):
    def test_foo(self):
        assert True
    