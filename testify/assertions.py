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
from __future__ import with_statement

import re

import contextlib

from .utils import stringdiffer


__testify = 1


def _val_subtract(val1, val2, dict_subtractor, list_subtractor):
    """
    Find the difference between two container types

    Returns:

    The difference between the values as defined by list_subtractor() and
    dict_subtractor() if both values are the same container type.

    None if val1 == val2
    val1 if type(val1) != type(val1)
    Otherwise - the difference between the values
    """

    if val1 == val2:
        # if the values are the same, return a degenerate type
        # this case is not used by list_subtract or dict_subtract
        return type(val1)()

    if isinstance(val1, dict) and isinstance(val2, dict):
        val_diff = dict_subtractor(val1, val2)
    elif isinstance(val1, (list, tuple)) and isinstance(val2, (list, tuple)):
        val_diff = list_subtractor(val1, val2)
    else:
        val_diff = val1

    return val_diff


def _dict_subtract(dict1, dict2):
    """
    Return key,value pairs from dict1 that are not in dict2

    Returns:
    A new dict 'res_dict' with the following properties:

    For all (key, val) pairs where key appears in dict2:

    if dict1[val] == dict2[val] then res_dict[val] is not defined
    else res_dict[val] == dict1[val]

    If vals are themselves dictionaries the algorim is applied recursively.

    Example:
        _dict_subtract({
                       1: 'one',
                       2: 'two',
                       3: {'a': 'A', 'b': 'B'},
                       4: {'c': 'C', 'd': 'D'}
                      },
                      {
                       2: 'two',
                       3: {'a': 'A', 'b': 'B'},
                       4: {'d': 'D'},
                       5: {'e': 'E'}
                      }) => {1: 'one', 4: {'c': 'C'}}
    """

    # make a result we can edit
    result = dict(dict1)

    # find the common keys -- i.e., the ones we might need to subtract
    common_keys = set(dict1.keys()) & set(dict2.keys())
    for key in common_keys:
        val1, val2 = dict1[key], dict2[key]

        if val1 == val2:
            # values are the same: subtract
            del result[key]
        else:
            # values are different: set the output key to the different between the values
            result[key] = _val_subtract(val1, val2, _dict_subtract, _list_subtract)

    return result


def _list_subtract(list1, list2):
    """
    Returns the difference between list1 and list2.

    _list_subtract([1,2,3], [3,2,1]) == [1,3]

    If any items in the list are container types, the method recursively calls
    itself or _dict_subtract() to subtract the child
    containers.
    """

    # call val_subtract on all items that are not the same
    res_list = [_val_subtract(val1, val2, _dict_subtract, _list_subtract)
                for val1, val2 in zip(list1, list2) if val1 != val2]

    # now append items that come after any item in list1
    res_list += list1[len(list2):]

    # return a tuple of list1 is a tuple
    if isinstance(list1, tuple):
        return tuple(res_list)
    else:
        return res_list


def assert_raises(*args, **kwargs):
    """Assert an exception is raised as a context manager or by passing in a
    callable and its arguments.

    As a context manager:
    >>> with assert_raises(Exception):
    ...     raise Exception

    Pass in a callable:
    >>> def raise_exception(arg, kwarg=None):
    ...     raise Exception
    >>> assert_raises(Exception, raise_exception, 1, kwarg=234)
    """
    if (len(args) == 1) and not kwargs:
        return _assert_raises_context_manager(args[0])
    else:
        return _assert_raises(*args, **kwargs)


@contextlib.contextmanager
def _assert_raises_context_manager(exception_class):
    try:
        yield
    except exception_class:
        return
    else:
        assert_not_reached("No exception was raised (expected %r)" %
                           exception_class)


def _assert_raises(exception_class, callable, *args, **kwargs):
    with _assert_raises_context_manager(exception_class):
        callable(*args, **kwargs)


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
    """Assert that lval and rval are equal."""
    if message:
        assert lval == rval, message
    else:
        assert lval == rval, \
            "assertion failed: l == r\nl: %r\nr: %r\n\n%s" % \
                (lval, rval, _diff_message(lval, rval))

assert_equals = assert_equal


def assert_almost_equal(lval, rval, digits, message=None):
    """Assert that lval and rval, when rounded to the specified number of digits, are the same."""
    real_message = message or "%r !~= %r" % (lval, rval)
    assert round(lval, digits) == round(rval, digits), real_message


def assert_within_tolerance(lval, rval, tolerance, message=None):
    """Assert that the difference between the two values, as a fraction of the left value, is smaller than the tolerance specified.
    That is, abs(float(lval) - float(rval)) / float(lval) < tolerance"""
    real_message = message or "%r !~= %r" % (lval, rval)
    assert abs(float(lval) - float(rval)) / float(lval) < tolerance, real_message


def assert_not_equal(lval, rval, message=None):
    """Assert that lval and rval are unequal to each other."""
    if message:
        assert lval != rval, message
    else:
        assert lval != rval, 'assertion failed: %r != %r' % (lval, rval)


def assert_lt(lval, rval, message=None):
    """Assert that lval is less than rval."""
    if message:
        assert lval < rval, message
    else:
        assert lval < rval, 'assertion failed: %r < %r' % (lval, rval)


def assert_lte(lval, rval, message=None):
    """Assert that lval is less than or equal to rval"""
    if message:
        assert lval <= rval, message
    else:
        assert lval <= rval, 'assertion failed: %r <= %r' % (lval, rval)


def assert_gt(lval, rval, message=None):
    """Assert that lval is greater than rval."""
    if message:
        assert lval > rval, message
    else:
        assert lval > rval, 'assertion failed: %r > %r' % (lval, rval)


def assert_gte(lval, rval, message=None):
    """Assert that lval is greater than or equal to rval"""
    if message:
        assert lval >= rval, message
    else:
        assert lval >= rval, 'assertion failed: %r >= %r' % (lval, rval)


def assert_in_range(val, start, end, message=None, inclusive=False):
    """Assert that val is greater than start and less than end. If inclusive is true, val may be equal to start or end."""
    if inclusive:
        real_message = message or "! %s <= %r <= %r" % (start, val, end)
        assert start <= val <= end, real_message
    else:
        real_message = message or "! %s < %r < %r" % (start, val, end)
        assert start < val < end, real_message


def assert_between(a, b, c):
    """Assert that b is between a and c, inclusive."""
    assert_in_range(b, a, c, inclusive=True)


def assert_in(item, sequence, msg="assertion failed: expected %(item)r in %(sequence)r"):
    """Assert that the item is in the sequence."""
    assert item in sequence, msg % {'item':item, 'sequence':sequence}


def assert_not_in(item, sequence, msg="assertion failed: expected %(item)r not in %(sequence)r"):
    """Assert that the item is not in the sequence."""
    assert item not in sequence, msg % {'item':item, 'sequence':sequence}


def assert_all_in(left, right):
    """Assert that everything in `left` is also in `right`
    Note: This is different than `assert_subset()` because python sets use
    `__hash__()` for comparision whereas `in` uses `__eq__()`.
    """
    unmatching = []
    for item in left:
        if item not in right:
            unmatching.append(item)
    if unmatching:
        raise AssertionError(
            'The following items were not found in not found in %s: %s' % (right, unmatching)
        )


def assert_starts_with(val, prefix):
    """Assert that val.startswith(prefix)."""
    msg = "%(val)r does not start with %(prefix)r" % locals()
    assert val.startswith(prefix), msg


def assert_not_reached(message=None):
    """Raise an AssertionError with a message."""
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


def assert_length(sequence, expected, message=None):
    """Assert a sequence or iterable has an expected length."""
    message = message or "%(sequence)s has length %(length)s expected %(expected)s"
    length = len(list(sequence))
    assert length == expected, message % locals()


def assert_call(turtle, call_idx, *args, **kwargs):
    """Assert that a function was called on turtle with the correct args."""
    actual = turtle.calls[call_idx] if turtle.calls else None
    msg = "Call %s expected %s, was %s" % (call_idx, (args, kwargs), actual)
    assert actual == (args, kwargs), msg


def assert_is(left, right, msg="expected %(left)r is %(right)r"):
    """Assert that left and right are the same object"""
    assert left is right, msg % {'left':left, 'right': right}


def assert_is_not(left, right, msg="expected %(left)r is not %(right)r"):
    """Assert that left and right are the same object"""
    assert left is not right, msg % {'left':left, 'right':right}


def assert_all_match_regex(pattern, values, msg="expected %(value)r to match %(pattern)r"):
    """Assert that all values in an iterable match a regex pattern.

    Args:
    pattern -- a regex.
    values -- an iterable of values to test.

    Raises AssertionError if any value does not match.

    """
    for value in values:
        assert re.match(pattern, value), msg % {'value':value, 'pattern':pattern}


def assert_match_regex(pattern, value, *args, **kwargs):
    """Assert that a single value matches a regex pattern."""
    assert_all_match_regex(pattern, [value], *args, **kwargs)


def assert_any_match_regex(pattern, values, msg="expected at least one %(values)r to match %(pattern)r"):
    """Assert that at least one value in an iterable matches a regex pattern.

    Args:
    pattern -- a regex.
    values -- an iterable of values to test.

    Raises AssertionError if all values don't match.

    """
    for value in values:
        if re.match(pattern, value) is not None:
            return

    raise AssertionError(msg % {'values':values, 'pattern':pattern})


def assert_all_not_match_regex(pattern, values, msg="expected %(value)r to not match %(pattern)r"):
    """Assert that all values don't match a regex pattern.

    Args:
    pattern -- a regex.
    values -- an iterable of values to test.

    Raises AssertionError if any values matches.

    """
    for value in values:
        assert not re.match(pattern, value), msg % {'value':value, 'pattern':pattern}


def assert_sets_equal(left, right, msg="expected %(left)r == %(right)r [left has:%(extra_left)r, right has:%(extra_right)r]"):
    """Assert that two sets are equal."""
    if left != right:
        extra_left = left - right
        extra_right = right - left
        raise AssertionError(msg % {
            'left': left,
            'right': right,
            'extra_left': extra_left,
            'extra_right': extra_right,
        })


def assert_dicts_equal(left, right, ignore_keys=None, msg="expected %(left)r == %(right)r [left has:%(extra_left)r, right has:%(extra_right)r]"):
    """Assert that two dictionarys are equal (optionally ignoring certain keys)."""
    if ignore_keys is not None:
        left = dict((k, left[k]) for k in left if k not in ignore_keys)
        right = dict((k, right[k]) for k in right if k not in ignore_keys)

    if left == right:
        return

    extra_left = _dict_subtract(left, right)
    extra_right = _dict_subtract(right, left)
    raise AssertionError(msg % {
        'left': left,
        'right': right,
        'extra_left': extra_left,
        'extra_right': extra_right,
    })


def assert_dict_subset(left, right, msg="expected [subset has:%(extra_left)r, superset has:%(extra_right)s]"):
    """Assert that a dictionary is a strict subset of another dictionary (both keys and values)."""
    difference_dict = _dict_subtract(left, right)

    if not difference_dict:
        return

    extra_left = difference_dict
    small_right = dict((k, right[k]) for k in right if k in left.keys())
    extra_right = _dict_subtract(small_right, left)
    raise AssertionError(msg % {
        'left': left,
        'right': right,
        'extra_left': extra_left,
        'extra_right': extra_right,
    })


def assert_subset(left, right, msg="expected %(set_left)r <= %(set_right)r [left has:%(extra)r]"):
    """Assert that the left set is a subset of the right set."""
    set_left = set(left)
    set_right = set(right)
    if not (set_left <= set_right):
        extra = set_left - set_right
        raise AssertionError(msg % {
            'left': left,
            'right': right,
            'set_left': set_left,
            'set_right': set_right,
            'extra': extra,
        })


def assert_list_prefix(left, right):
    """Assert that the left list is a prefix of the right list."""
    assert_equal(left, right[:len(left)])


def assert_sorted_equal(left, right, **kwargs):
    """Assert equality, but without respect to ordering of elements. Basically for multisets."""
    assert_equal(sorted(left), sorted(right), **kwargs)


def assert_isinstance(object_, type_):
    """Assert that an object is an instance of a given type."""
    assert isinstance(object_, type_), "Expected type %r but got type %r" % (type_, type(object_))


def assert_datetimes_equal(a, b):
    """Tests for equality of times by only testing up to the millisecond."""
    assert_equal(a.utctimetuple()[:-3], b.utctimetuple()[:-3], "%r != %r" % (a, b))


def assert_exactly_one(*args, **kwargs):
    """Assert that only one of the given arguments passes the provided truthy function (non-None by default).

    Args:
        truthy_fxn: a filter to redefine truthy behavior. Should take an object and return
        True if desired conditions are satisfied. For example:

        >>> assert_exactly_one(True, False, truthy_fxn=bool) # Success

        >>> assert_exactly_one(0, None) # Success

        >>> assert_exactly_one(True, False)
        AssertionError

    Returns:
        The argument that passes the truthy function
    """
    truthy_fxn = kwargs.pop('truthy_fxn', lambda x: x is not None)
    assert not kwargs, "Unexpected kwargs: %r" % kwargs

    true_args = [arg for arg in args if truthy_fxn(arg)]
    if len(true_args) != 1:
        raise AssertionError("Expected exactly one True (got %d) args: %r" % (len(true_args), args))

    return true_args[0]
