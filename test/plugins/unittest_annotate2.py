import testify
import mock
from testify import suite
from testify import assert_in
from testify.plugins.unittest_annotate2 import prepare_test_case
from testify.plugins.unittest_annotate2 import order_tests
class TestCaseMixin(testify.TestCase):
    """A mixin for building testcases"""

    def __init__(self, *args, **kwargs):
        testify.TestCase.__init__(self, *args, **kwargs)
        self.test1_unit = 0
        self.test2_unit = 0
        self.test3_unit = 0


    @suite('test_suite')
    @suite('unittest')
    def test1(self):
        self.test1_unit += 1

    @suite('notunit')
    def test2(self):
        if self.test1_unit:
            self.test2_unit += 1
        if self.test3_unit:
            self.test2_unit += 1
    @suite('unittest')
    def test3(self):
        self.test3_unit += 1

class GeneratorTest(testify.TestCase):
    """
    Tests the generator used for discovered_tests
    """

    @testify.setup
    def setup(self):
        # Build a test case with a mixture
        mixture = TestCaseMixin()
        self.testcases = [mixture]
         
    def test_mixture(self):
        """Test that all units run first"""
        prepare_test_case(mock.Mock(), self.testcases[0])
        for test_case in self.testcases:
            test_case.run()
            
            # Expecting only unit tests 
            self.assertEqual(test_case.test1_unit, 1)
            self.assertEqual(test_case.test3_unit, 1)
            self.assertEqual(test_case.test2_unit, 2)      

    def test_prepare(self):
        testcase = self.testcases[0]
        prepare_test_case(mock.Mock(), testcase)
        has_order = hasattr(testcase, 'order_tests')
        self.assertEqual(has_order, True)

    def test_order_tests(self):
        testcase = self.testcases[0]
        for method in testcase.runnable_test_methods():
            member_suites = testcase.suites(method)
            isunit = order_tests(member_suites)
            expected = 'unittest' in member_suites
            self.assertEqual(isunit, expected)
             
             
