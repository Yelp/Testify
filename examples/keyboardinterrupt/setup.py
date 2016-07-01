"""this example throws KeyboardInterrupt during fixture setup"""
import testify as T


class Test(T.TestCase):
    def setUp(self):
        raise KeyboardInterrupt('fake!')

    def test1(self):
        pass

    def test2(self):
        pass
