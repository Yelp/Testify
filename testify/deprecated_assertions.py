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


__testify = 1


def fail(self, msg=None):
    """Fail immediately, with the given message."""
    raise AssertionError(msg)


def failIf(self, expr, msg=None):
    "Fail the test if the expression is true."
    if expr:
        raise AssertionError(msg)


def failUnless(self, expr, msg=None):
    """Fail the test unless the expression is true."""
    if not expr:
        raise AssertionError(msg)


def failUnlessRaises(self, excClass, callableObj, *args, **kwargs):
    """Fail unless an exception of class excClass is thrown
       by callableObj when invoked with arguments args and keyword
       arguments kwargs. If a different type of exception is
       thrown, it will not be caught, and the test case will be
       deemed to have suffered an error, exactly as for an
       unexpected exception.
    """
    try:
        callableObj(*args, **kwargs)
    except excClass:
        return
    else:
        if hasattr(excClass, '__name__'):
            excName = excClass.__name__
        else:
            excName = str(excClass)
        raise AssertionError("%s not raised" % excName)


def failUnlessEqual(self, first, second, msg=None):
    """Fail if the two objects are unequal as determined by the '=='
       operator.
    """
    if not first == second:
        raise AssertionError(msg or '%r != %r' % (first, second))


def failIfEqual(self, first, second, msg=None):
    """Fail if the two objects are equal as determined by the '=='
       operator.
    """
    if first == second:
        raise AssertionError(msg or '%r == %r' % (first, second))


def failUnlessAlmostEqual(self, first, second, places=7, msg=None):
    """Fail if the two objects are unequal as determined by their
       difference rounded to the given number of decimal places
       (default 7) and comparing to zero.

       Note that decimal places (from zero) are usually not the same
       as significant digits (measured from the most signficant digit).
    """
    if round(second - first, places) != 0:
        raise AssertionError(msg or '%r != %r within %r places' % (first, second, places))


def failIfAlmostEqual(self, first, second, places=7, msg=None):
    """Fail if the two objects are equal as determined by their
       difference rounded to the given number of decimal places
       (default 7) and comparing to zero.

       Note that decimal places (from zero) are usually not the same
       as significant digits (measured from the most signficant digit).
    """
    if round(second - first, places) == 0:
        raise AssertionError(msg or '%r == %r within %r places' % (first, second, places))

# Synonyms for assertion methods


# stop using these
assertEqual = assertEquals = failUnlessEqual
# stop using these
assertNotEqual = assertNotEquals = failIfEqual

assertAlmostEqual = assertAlmostEquals = failUnlessAlmostEqual

assertNotAlmostEqual = assertNotAlmostEquals = failIfAlmostEqual

assertRaises = failUnlessRaises

assert_ = assertTrue = failUnless

assertFalse = failIf
