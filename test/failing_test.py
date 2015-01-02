
import testify as T


@T.suite('fake')
class FailingTest(T.TestCase):
    """This is used for an integration test showing failures trigger nonzero
    return values.
    """

    def test_failing(self):
        assert False
