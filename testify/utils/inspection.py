# Copyright 2012 Yelp
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

"""Helpers for dealing with class and method introspection.

In particular, these functions help to remedy differences in behavior between
Python 2.6.x and 2.7.3+ when getting/setting attributes on instancemethods.

Attributes can be freely set on functions, but not instancemethods. Because we
juggle methods and functions often interchangably, these produce the desired
effect of setting (or getting) the attribute on the function regardless of our
callable's type.
"""

import inspect
import types

import six


def callable_hasattr(callable_, attr_name):
    function = get_function(callable_)
    return hasattr(function, attr_name)


def callable_setattr(callable_, attr_name, attr_value):
    function = get_function(callable_)
    setattr(function, attr_name, attr_value)


def get_function(callable_):
    """If given a method, returns its function object; otherwise a no-op."""
    if isinstance(callable_, types.MethodType):
        return six.get_method_function(callable_)
    return callable_


def is_fixture_method(callable_):
    """Whether Testify has decorated this callable as a test fixture."""
    # ensure we don't pick up turtles/mocks as fixtures
    if not inspect.isroutine(callable_):
        return False

    # _fixture_id indicates this method was tagged by us as a fixture
    return callable_hasattr(callable_, '_fixture_type')
