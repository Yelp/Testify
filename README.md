# Testify - A Testing Framework

Testify is a replacement for Python's unittest module and nose. It is modeled
after unittest, and existing unittest classes are fully supported.

However, Testify has features above and beyond unittest:

  - Class-level setup and teardown fixture methods, which are run only once for
    an entire class of test methods.

  - A decorator-based approach to fixture methods, enabling features like
    lazily-evaluated attributes and context managers for tests.

  - Enhanced test discovery. Testify can drill down into packages to find test
    cases (similiar to nose).

  - Support for detecting and running test suites, grouped by modules,
    classes, or individual test methods.

  - Support for splitting up tests into buckets for multiprocessing.

  - Pretty test runner output (hooray color!).

  - Extensible plugin system for adding additional functionality around
    reporting.

  - Comes complete with other handy testing utilities, including turtle (for
    mocking), code coverage integration, profiling, and numerous common
    assertion helpers for easier debugging.

  - More pythonic naming conventions.

### Example Test Case

```python
from testify import *

class AdditionTestCase(TestCase):

    @class_setup
    def init_the_variable(self):
        self.variable = 0

    @setup
    def increment_the_variable(self):
        self.variable += 1

    def test_the_variable(self):
        assert_equal(self.variable, 1)

    @suite('disabled', reason='ticket #123, not equal to 2 places')
    def test_broken(self):
        # raises 'AssertionError: 1 !~= 1.01'
        assert_almost_equal(1, 1.01, threshold=2)

    @teardown
    def decrement_the_variable(self):
        self.variable -= 1

    @class_teardown
    def get_rid_of_the_variable(self):
        self.variable = None

if __name__ == "__main__":
    run()
```

