import sys
import time
import testify as T


def wait():
    # We need this test to wait until we have two clients connected.
    # We accomplish this by sleeping until sigint is sent
    try:
        sys.stdout.write('ready!\n')
        sys.stdout.flush()
        # Poppies will put them to sleeeep!
        time.sleep(99999999)
    except KeyboardInterrupt:
        pass


@T.suite('fake')
class TestCase1(T.TestCase):
    def test_fail(self):
        wait()
        raise AssertionError('Intentional failure!')


@T.suite('fake')
class TestCase2(T.TestCase):
    def test_pass(self):
        wait()
