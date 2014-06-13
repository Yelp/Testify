import pdb
from copy import copy

def remove_tests(testcase, suite_name):
    for method_name in dir(testcase):
        if method_name.startswith("test"):
            # Get all suites for method
            method = getattr(testcase, method_name) 
            suites = testcase.suites(method)
            
            # If marked by suite, delete it
            if suite_name in suites:
                delattr(testcase, method_name)

def unittest_seperator(discovered_tests):
    final_tests = []
    for test in discovered_tests:
        # Build brand new test cases
        unitcase = copy(test)
        notunitcase = copy(test)

        # Remove test methods from each
        remove_tests(unitcase, 'notunit')
        remove_tests(notunitcase, 'unittest') 

        final_tests.append(unitcase)
        final_tests.append(notunitcase)

    return final_tests

def generator(discovered_tests):
    for testcase in discovered_tests:
        if not hasattr(testcase, '_TestCase__suites_exclude'):
            testcase._TestCase__suites_exclude = set()

        testcase._TestCase__suites_exclude.add('notunit')
        yield testcase

    for testcase in discovered_tests:
        # If binned, testcase may not have been primed
        if not hasattr(testcase, '_TestCase__suites_exclude'):
            testcase._TestCase__suites_exclude = set('notunit')

        if 'notunit' in testcase._TestCase__suites_exclude:
            testcase._TestCase__suites_exclude.remove('notunit')

        testcase._TestCase__suites_exclude.add('unittest')

        yield testcase

def order_tests(method_suites):
    if 'unittest' in method_suites:
        return True
    else:
        return False

def prepare_test_case(options, testcase):
    testcase.order_tests = order_tests

# def rearrange_discovered_tests(options, discovered_tests):
    # return iter(generator(discovered_tests))
