"""this example throws KeyboardInterrupt during fixture teardown"""
import testify as T


class Test(T.TestCase):
    @T.setup_teardown
    def fixture(self):
        yield
        raise KeyboardInterrupt('fake!')

    def test1(self):
        pass

    def test2(self):
        pass
