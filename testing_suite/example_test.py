
from testify import TestCase, run


class ExampleTestCase(TestCase):

    def test_one(self):
        pass

    def test_two(self):
        pass


class SecondTestCase(TestCase):

    def test_one(self):
        pass


if __name__ == "__main__":
    run()
