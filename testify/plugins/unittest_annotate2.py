def order_tests(method_suites):
    if 'unittest' in method_suites:
        return True
    else:
        return False

def prepare_test_case(options, testcase):
    testcase.order_tests = order_tests

