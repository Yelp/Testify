import testify as T


@T.suite('fake')
class FailingTestInterrupt(T.TestCase):
    def test(self):
        raise KeyboardInterrupt
