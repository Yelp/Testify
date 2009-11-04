# Copyright 2009 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


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
