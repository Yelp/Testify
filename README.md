# Testify - A Testing Framework

*PLEASE NOTE:* Yelp is in the process of switching to [py.test](http://pytest.org/). We recommend you use it instead of Testify.

[![Build Status](https://travis-ci.org/Yelp/Testify.png?branch=master)](https://travis-ci.org/Yelp/Testify)

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

  - Pretty test runner output (hooray color!).

  - Extensible plugin system for adding additional functionality around
    reporting.

  - Comes complete with other handy testing utilities, including turtle (for
    mocking), code coverage integration, profiling, and numerous common
    assertion helpers for easier debugging.

  - More Pythonic naming conventions.

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

### Unittest Compatibility

Testify will discover and run ``unittests`` without any code changes, just
point it to a directory containing your tests:

```bash
$ testify my_unittests/foo_test.py
```

To take advantage of more advanced Testify features, just replace
``unittest.TestCase`` with ``testify.TestCase``!

### Fixtures

Testify provides the following fixtures for your enjoyment:

  - ``@setup``: Run before each individual test method on the ``TestCase``(that
    is, all methods that begin with 'test').

  - ``@teardown``: Like ``setup``, but run after each test completes
    (regardless of success or failure).

  - ``@class_setup``: Run before a ``TestCase`` begins executing its tests.
    Note that this not a class method; you still have access to the same
    ``TestCase`` instance as your tests.

  - ``@class_teardown``: Like ``class_setup``, but run after all tests complete
    (regardless of success or failure).

  - ``@setup_teardown``: A context manager for individual tests, where test
    execution occurs during the yield. For example:

    ```python
    @setup_teardown
    def mock_something(self):
        with mock.patch('foo') as foo_mock:
            self.foo_mock = foo_mock
            yield
        # this is where you would do teardown things
    ```

  - ``@class_setup_teardown``: Like ``setup_teardown``, but all of the
    ``TestCase``'s methods are run when this yields.

  - ``@let``: This declares a lazily-evaluated attribute of the ``TestCase``.
    When accessed, this attribute will be computed and cached for the life of
    the test (including setup and teardown). For example:

    ```python
    @let
    def expensive_attribute(self):
      return expensive_function_call()

    def test_something(self):
      assert self.expensive_attribute

    def test_something_else(self):
      # no expensive call
      assert True
    ```

#### Order of Execution

In pseudo code, Testify follows this schedule when running your tests:

```
   Run all 'class_setup' methods
   Enter all 'class_setup_teardown' context managers
   For each method beginning with 'test':
       Run all 'setup' methods
       Enter all 'setup_teardown' context managers
           Run the method and record failure or success
       Exit all 'setup_teardown' context managers
       Run all 'teardown' methods
   Exit all 'class_setup_teardown' context managers
   Run all 'class_teardown' methods
```

##### ...When Subclassing

Your fixtures are just decorated methods, so they can be inherited and
overloaded as expected. When you introduce subclasses and mixins into the...
mix, things can get a little crazy. For this reason, Testify makes a couple
guarantees about how your fixtures are run:

 * A subclass's fixture context is always contained within its parent's fixture
   context (as determined by the usual
   [MRO](http://www.python.org/download/releases/2.3/mro/)). That is, fixture
   context is pushed and popped in FILO order.

 * Fixtures of the same type (and defined at the same level in the class
   heirarchy) will be run in the order they are defined on the class.
