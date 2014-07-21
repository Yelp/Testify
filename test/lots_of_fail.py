import sys
import testify as T


_suites = ['fake']


class Fail(T.TestCase):
    def test(self):
        assert False


# Make a bunch of failing tests
for i in range(25):
    class FailChild(Fail):
        pass

    FailChild.__name__ = 'Fail{0}'.format(i)
    setattr(sys.modules[__name__], FailChild.__name__, FailChild)
