"""this example throws SystemExit during testing"""
import testify as T
import sys


class Test(T.TestCase):
    def test(self):
        sys.exit('fake!')
