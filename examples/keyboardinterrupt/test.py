"""this example throws KeyboardInterrupt during testing"""
import testify as T


class Test(T.TestCase):
    def test1(self):
        raise KeyboardInterrupt('fake!')

    def test2(self):
        raise KeyboardInterrupt('fake!')
