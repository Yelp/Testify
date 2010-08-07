Testify - A Testing Framework

Testify is a replacement for Python's unittest module and nose. It is modeled after unittest, and tests written for unittest
will run under testify with a minimum of adjustments, but it has features above and beyond unittest:

  - class-level setup and teardown fixture methods which are run once each for an entire set of test methods.
  - a decorator-based approach for fixture methods, eliminating the need for super() calls.
  - More pythonic, less java
  - enhanced test discovery - testify can drill down into packages to find test cases (similiar to nose).
  - support for collecting and running tests by collecting modules, classes or methods into test suites.
  - Pretty test runner output (color!)
  - Support for splitting up tests into buckets to support multi-processing
  - Extensible plugin system for adding additional functionality around reporting
  - Comes complete with other handy testing utilities: Mocking (turtle), code coverage integration and profiling.

an example test case module:
---
from testify import *
class AdditionTestCase(TestCase):
    @class_setup
    def init_the_variable(self):
        self.variable = 0

    @setup
    def increment_the_variable(self):
        self.variable += 1

    def test_the_variable(self):
        assert self.variable == 1

    @teardown
    def decrement_the_variable(self):
        self.variable -= 1

    @class_teardown
    def get_rid_of_the_variable(self):
        self.variable = None

if __name__ == "__main__":
    run()

