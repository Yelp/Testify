import os
import os.path
import time
import testify as T


def wait():
    # We need this test to wait until we have two clients connected.
    # We accomplish this by sleeping until we see 'go!'
    with open(os.environ['client_num'], 'w') as f:
        f.write('ready!')

    while not os.path.exists('go!'):
        time.sleep(.001)


@T.suite('fake')
class TestCase1(T.TestCase):
    def test_fail(self):
        wait()
        raise AssertionError('Intentional failure!')


@T.suite('fake')
class TestCase2(T.TestCase):
    def test_pass(self):
        wait()
