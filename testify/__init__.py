"""A custom framework for running tests.

The basic components of this system are:

    - TestCase
        a class which contains test methods and fixture methods (setup/teardown etc),
        executes these test methods when told to and collects information on their
        run status, including timing and success/failure

    - TestRunner
        a class which collects TestCase subclasses based on search criteria and asks them
        to kindly execute themselves.
"""
__author__ = "Oliver Nicholas <bigo@yelp.com>"
__testify = 1

from assertions import *

from test_case import (
   						MetaTestCase,
   						TestCase,
   						class_setup,
   						setup,
   						teardown,
   						class_teardown,
   						suite)

# print "testify says: %s" % test_case
# # from test_discovery import discover
# from test_runner import TestRunner, run_tests
# import test_program
