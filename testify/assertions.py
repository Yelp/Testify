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


"""Methods to be used inside of assert statements"""

from .utils import stringdiffer


__testify = 1

def assert_raises(expected_exception_class, callable_obj, *args, **kwargs):
    """Returns true only if the callable raises expected_exception_class"""
    try:
        callable_obj(*args, **kwargs)
    except expected_exception_class:
        # we got the expected exception
        return True
    assert_not_reached("No exception was raised (expected %s)" % expected_exception_class)

def _diff_message(lhs, rhs):
    """If `lhs` and `rhs` are strings, return the a formatted message
    describing their differences. If they're not strings, describe the
    differences in their `repr()`s.

    NOTE: Only works well for strings not containing newlines.
    """
    lhs = repr(lhs) if not isinstance(lhs, basestring) else lhs
    rhs = repr(rhs) if not isinstance(rhs, basestring) else rhs

    return 'Diff:\nl: %s\nr: %s' % stringdiffer.highlight(lhs, rhs)

def assert_equal(lval, rval, message=None):
    if message:
        assert lval == rval, message
    else:
        assert lval == rval, \
            "assertion failed: l == r\nl: %r\nr: %r\n\n%s" % \
                (lval, rval, _diff_message(lval, rval))

assert_equals = assert_equal

def assert_almost_equal(lval, rval, digits, message=None):
    real_message = message or "%r !~= %r" % (lval, rval)
    assert round(lval, digits) == round(rval, digits), real_message

def assert_within_tolerance(lval, rval, tolerance, message=None):
    real_message = message or "%r !~= %r" % (lval, rval)
    assert abs(float(lval) - float(rval)) / float(lval) < tolerance, real_message

def assert_not_equal(lval, rval, message=None):
    if message:
        assert lval != rval, message
    else:
        assert lval != rval, 'assertion failed: %s != %s' % (lval, rval)

def assert_lt(lval, rval, message=None):
    if message:
        assert lval < rval, message
    else:
        assert lval < rval, 'assertion failed: %s < %s' % (lval, rval)

def assert_lte(lval, rval, message=None):
    if message:
        assert lval <= rval, message
    else:
        assert lval <= rval, 'assertion failed: %s lte %s' % (lval, rval)

def assert_gt(lval, rval, message=None):
    if message:
        assert lval > rval, message
    else:
        assert lval > rval, 'assertion failed: %s > %s' % (lval, rval)

def assert_gte(lval, rval, message=None):
    if message:
        assert lval >= rval, message
    else:
        assert lval >= rval, 'assertion failed: %s >= %s' % (lval, rval)

def assert_in_range(val, start, end, message=None, inclusive=False):
    if inclusive:
        real_message = message or "! %s <= %r <= %r" % (start, val, end)
        assert start <= val <= end, real_message
    else:
        real_message = message or "! %s < %r < %r" % (start, val, end)
        assert start < val < end, real_message

def assert_in(item, sequence):
    assert item in sequence, "assertion failed: expected %r in %r" % (item, sequence)

def assert_not_in(item, sequence):
    assert item not in sequence, "assertion failed: expected %r not in %r" % (item, sequence)

def assert_starts_with(val, prefix):
    msg = "%(val)r does not start with %(prefix)r" % locals()
    assert val.startswith(prefix), msg

def assert_not_reached(message=None):
    if message:
        assert False, message
    else:
        assert False, 'egads! this line ought not to have been reached'

def assert_rows_equal(rows1, rows2):
    """Check that two sequences contain the same lists of dictionaries"""

    def norm_row(row):
        if isinstance(row, dict):
            return tuple((k, row[k]) for k in sorted(row))
        else:
            return tuple(sorted(row))

    def norm_rows(rows):
        return tuple(sorted(norm_row(row) for row in rows))

    assert_equal(norm_rows(rows1), norm_rows(rows2))
