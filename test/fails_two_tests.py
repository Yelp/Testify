import testify as T


@T.suite('fake')
class FailsTwoTests(T.TestCase):
    def test1(self):
        assert False

    def test2(self):
        assert False
