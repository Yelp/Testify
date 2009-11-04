Testify is a replacement for Python 2's unittest module.  It is modeled after unittest, and tests written for unittest will run under testify with a minimum of adjustments, but it has features above and beyond unittest:

  - enhanced test discovery - testify can drill down into packages to find test cases.
  - class-level setup and teardown fixture methods which are run once each for an entire set of test methods.
  - a decorator-based approach for fixture methods, eliminating the need for super() calls.
  - Logging output in color
  - A decorator-based approach to temporarily disabling certain tests, which strongly encourages documentation and eventual fixing of bugs.

an example test case module:
---
from testify import *
class AdditionTestCase(TestCase):
    @class_setup
    def __init_the_variable(self):
        self.variable = 0

    @setup
    def __increment_the_variable(self):
        self.variable += 1

    def test_the_variable(self):
        assert self.variable == 1

    @teardown
    def ___decrement_the_variable(self):
        self.variable -= 1

    @class_teardown
    def __get_rid_of_the_variable(self):
        self.variable = None

if __name__ == "__main__":
    run_tests()
---

