# Copyright 2009-2011 Yelp
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
# flake8: noqa
from __future__ import absolute_import
import warnings
from .test_program import TestProgram, main, run
from .utils import turtle
from .test_fixtures import (
    class_setup,
    setup,
    teardown,
    class_teardown,
    setup_teardown,
    class_setup_teardown,
    suite,
    let,
)
from .test_case import (
    MetaTestCase,
    TestCase,
)
from .exceptions import TestifyError
from .assertions import *
__testify = 1
__version__ = "0.11.0"


# We want default warning behavior for DeprecationWarning's thrown within testify.
# This gives consistent behavior (and makes our tests pass) under python2.7.
warnings.filterwarnings('default', module=r'^testify(\.|$)', category=DeprecationWarning)
