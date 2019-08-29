# -*- coding: utf-8 -*-
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
import contextlib
from itertools import islice
import re
import warnings

import six

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


def assert_raises_such_that(exception_class, exception_test=lambda e: e, callable_obj=None, *args, **kwargs):
    """
    Assert that an exception is raised such that expection_test(exception)
    passes, either in a with statement via a context manager or while calling
    a given callable on given arguments.

    Arguments:
        exception_class - class corresponding to the expected exception
        exception_test - a callable which takes an exception instance and
            asserts things about it
        callable_obj, *args, **kwargs - optional, a callable object and
            arguments to pass into it which when used are expected to raise the
            exception; if not provided, this function returns a context manager
            which will check that the assertion is raised within the context
            (the body of the with statement).

    As a context manager:
    >>> says_whatever = lambda e: assert_equal(str(e), "whatever")
    >>> with assert_raises_such_that(Exception, says_whatever):
    ...     raise Exception("whatever")

    Pass in a callable:
    >>> says_whatever = lambda e: assert_equal(str(e), "whatever")
    >>> def raise_exception(arg, kwarg=None):
    ...     raise Exception("whatever")
    >>> assert_raises_such_that(Exception, says_whatever, raise_exception, 1, kwarg=234)
    """
    if callable_obj is None:
        return _assert_raises_context_manager(exception_class, exception_test)
    else:
        with _assert_raises_context_manager(exception_class, exception_test):
            callable_obj(*args, **kwargs)


def assert_raises_exactly(exception_class, *args):
    """
    Assert that a particular exception_class is raised with particular arguments.
    Use this assertion when the exception message is important.
    """
    def test_exception(exception):
        # We want to know the exact exception type, not that it has some superclass.
        assert_is(type(exception), exception_class)
        assert_equal(exception.args, args)

    return assert_raises_such_that(exception_class, test_exception)


def assert_raises_and_contains(expected_exception_class, strings, callable_obj, *args, **kwargs):
    """Assert an exception is raised by passing in a callable and its
    arguments and that the string representation of the exception
    contains the case-insensitive list of passed in strings.

    Args
        strings -- can be a string or an iterable of strings
    """
    try:
        callable_obj(*args, **kwargs)
    except expected_exception_class as e:
        message = str(e).lower()
        try:
            is_string = isinstance(strings, basestring)
        except NameError:
            is_string = isinstance(strings, str)
        if is_string:
            strings = [strings]
        for string in strings:
            assert_in(string.lower(), message)
    else:
        assert_not_reached("No exception was raised (expected %s)" % expected_exception_class)


@contextlib.contextmanager
def _assert_raises_context_manager(exception_class, exception_test=lambda e: e):
    """Builds a context manager for testing that code raises an assertion.

    Args:
        exception_class - a subclass of Exception
        exception_test - optional, a function to apply to the exception (to
            test something about it)
    """
    try:
        yield
    except exception_class as e:
        exception_test(e)
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
    lhs = _to_characters(lhs)
    rhs = _to_characters(rhs)

    message = u'Diff:\nl: %s\nr: %s' % stringdiffer.highlight(lhs, rhs)
    # Python2 exceptions require bytes.
    if six.PY2:
        return message.encode('UTF-8')
    else:
        return message


def assert_equal(lval, rval, message=None):
    """Assert that lval and rval are equal."""
    if message:
        assert lval == rval, message
    else:
        assert lval == rval, \
            "assertion failed: l == r\nl: %r\nr: %r\n\n%s" % \
            (lval, rval, _diff_message(lval, rval))


assert_equals = assert_equal


def _get_msg(args, kwargs, suggestion):
    if args:
        raise TypeError(
            '`message` is kwargs only.  Perhaps you meant `{}`?'.format(
                suggestion,
            ),
        )
    message = kwargs.pop('message', None)
    if kwargs:
        raise TypeError('Unexpected kwargs {!r}'.format(kwargs))
    return message


def assert_truthy(lval, *args, **kwargs):
    """Assert that lval evaluates truthy, not identity."""
    message = _get_msg(args, kwargs, 'assert_equal')
    if message:
        assert lval, message
    else:
        assert lval, "assertion failed: l == r\nl: %r\nr: %r\n\n%s" % (
            lval, True, _diff_message(lval, True),
        )


def assert_falsey(lval, *args, **kwargs):
    """Assert that lval evaluates falsey, not identity."""
    message = _get_msg(args, kwargs, 'assert_not_equal')
    if message:
        assert not lval, message
    else:
        assert not lval, "assertion failed: l == r\nl: %r\nr: %r\n\n%s" % (
            lval, False, _diff_message(lval, False),
        )


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


def assert_in(item, sequence, message="assertion failed: expected %(item)r in %(sequence)r", msg=None):
    """Assert that the item is in the sequence."""
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    assert item in sequence, message % {'item': item, 'sequence': sequence}


def assert_not_in(item, sequence, message="assertion failed: expected %(item)r not in %(sequence)r", msg=None):
    """Assert that the item is not in the sequence."""
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    assert item not in sequence, message % {'item': item, 'sequence': sequence}


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
            'The following items were not found in %s: %s' % (right, unmatching)
        )


def assert_starts_with(val, prefix):
    """Assert that val.startswith(prefix)."""
    message = "%(val)r does not start with %(prefix)r" % locals()
    assert val.startswith(prefix), message


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


def assert_empty(iterable, max_elements_to_print=None, message=None):
    """
    Assert that an iterable contains no values.

    Args:
        iterable - any iterable object
        max_elements_to_print - int or None, maximum number of elements from
            iterable to include in the error message. by default, includes all
            elements from iterables with a len(), and 10 elements otherwise.
            if max_elements_to_print is 0, no sample is printed.
        message - str or None, custom message to print if the iterable yields.
            a sample is appended to the end unless max_elements_to_print is 0.
    """
    # Determine whether or not we can print all of iterable, which could be
    # an infinite (or very slow) generator.
    if max_elements_to_print is None:
        try:
            max_elements_to_print = len(iterable)
        except TypeError:
            max_elements_to_print = 10

    # Build the message *before* touching iterable since that might modify it.
    message = message or "iterable {} was unexpectedly non-empty.".format(iterable)

    # Get the first max_elements_to_print + 1 items from iterable, or just
    # the first item if max_elements_to_print is 0.  Trying to get an
    # extra item by adding 1 to max_elements_to_print lets us tell whether
    # we got everything in iterator, regardless of if it has len() defined.
    if max_elements_to_print == 0:
        sample = list(islice(iterable, 0, 1))
    else:
        sample_plus_extra = list(islice(iterable, 0, max_elements_to_print + 1))
        sample_is_whole_iterable = len(sample_plus_extra) <= max_elements_to_print
        sample = sample_plus_extra[:max_elements_to_print]

        if sample_is_whole_iterable:
            message += ' elements: %s' % sample
        else:
            message += ' first %s elements: %s' % (len(sample), sample)

    assert len(sample) == 0, message


def assert_not_empty(iterable, message=None):
    """
    Assert that an iterable is not empty (by trying to loop over it).

    Args:
        iterable - any iterable object
        message - str or None, message to print if the iterable doesn't yield
    """
    for value in iterable:
        break
    else:
        # The else clause of a for loop is reached iff you break out of the loop.
        raise AssertionError(message if message else
                             "iterable {} is unexpectedly empty".format(iterable)
                             )


def assert_length(sequence, expected, message=None):
    """Assert a sequence or iterable has an expected length."""
    message = message or "%(sequence)s has length %(length)s expected %(expected)s"
    length = len(list(sequence))
    assert length == expected, message % locals()


def assert_call(turtle, call_idx, *args, **kwargs):
    """Assert that a function was called on turtle with the correct args."""
    actual = turtle.calls[call_idx] if turtle.calls else None
    message = "Call %s expected %s, was %s" % (call_idx, (args, kwargs), actual)
    assert actual == (args, kwargs), message


def assert_is(left, right, message="expected %(left)r is %(right)r", msg=None):
    """Assert that left and right are the same object"""
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    assert left is right, message % {'left': left, 'right': right}


def assert_is_not(left, right, message="expected %(left)r is not %(right)r", msg=None):
    """Assert that left and right are NOT the same object"""
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    assert left is not right, message % {'left': left, 'right': right}


def assert_all_match_regex(pattern, values, message="expected %(value)r to match %(pattern)r", msg=None):
    """Assert that all values in an iterable match a regex pattern.

    Args:
    pattern -- a regex.
    values -- an iterable of values to test.

    Raises AssertionError if any value does not match.

    """
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    for value in values:
        assert re.match(pattern, value), message % {'value': value, 'pattern': pattern}


def assert_match_regex(pattern, value, *args, **kwargs):
    """Assert that a single value matches a regex pattern."""
    assert_all_match_regex(pattern, [value], *args, **kwargs)


def assert_any_match_regex(pattern, values, message="expected at least one %(values)r to match %(pattern)r", msg=None):
    """Assert that at least one value in an iterable matches a regex pattern.

    Args:
    pattern -- a regex.
    values -- an iterable of values to test.

    Raises AssertionError if all values don't match.

    """
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    for value in values:
        if re.match(pattern, value) is not None:
            return

    raise AssertionError(message % {'values': values, 'pattern': pattern})


def assert_all_not_match_regex(pattern, values, message="expected %(value)r to not match %(pattern)r", msg=None):
    """Assert that all values don't match a regex pattern.

    Args:
    pattern -- a regex.
    values -- an iterable of values to test.

    Raises AssertionError if any values matches.

    """
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    for value in values:
        assert not re.match(pattern, value), message % {'value': value, 'pattern': pattern}


def assert_sets_equal(
        left,
        right,
        message="expected %(left)r == %(right)r [left has:%(extra_left)r, right has:%(extra_right)r]",
        msg=None,
):
    """Assert that two sets are equal."""
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    if left != right:
        extra_left = left - right
        extra_right = right - left
        raise AssertionError(message % {
            'left': left,
            'right': right,
            'extra_left': extra_left,
            'extra_right': extra_right,
        })


def assert_dicts_equal(
        left,
        right,
        ignore_keys=None,
        message="expected %(left)r == %(right)r [left has:%(extra_left)r, right has:%(extra_right)r]",
        msg=None,
):
    """Assert that two dictionarys are equal (optionally ignoring certain keys)."""
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    if ignore_keys is not None:
        left = {k: left[k] for k in left if k not in ignore_keys}
        right = {k: right[k] for k in right if k not in ignore_keys}

    if left == right:
        return

    extra_left = _dict_subtract(left, right)
    extra_right = _dict_subtract(right, left)
    raise AssertionError(message % {
        'left': left,
        'right': right,
        'extra_left': extra_left,
        'extra_right': extra_right,
    })


def assert_dict_subset(left, right, message="expected [subset has:%(extra_left)r, superset has:%(extra_right)s]", msg=None):
    """Assert that a dictionary is a strict subset of another dictionary (both keys and values)."""
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    difference_dict = _dict_subtract(left, right)

    if not difference_dict:
        return

    extra_left = difference_dict
    small_right = {k: right[k] for k in right if k in left.keys()}
    extra_right = _dict_subtract(small_right, left)
    raise AssertionError(message % {
        'left': left,
        'right': right,
        'extra_left': extra_left,
        'extra_right': extra_right,
    })


def assert_subset(left, right, message="expected %(set_left)r <= %(set_right)r [left has:%(extra)r]", msg=None):
    """Assert that the left set is a subset of the right set."""
    if msg:
        warnings.warn("msg is deprecated", DeprecationWarning)
        message = msg

    set_left = set(left)
    set_right = set(right)
    if not (set_left <= set_right):
        extra = set_left - set_right
        raise AssertionError(message % {
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
        True

        >>> assert_exactly_one(0, None) # Success
        0

        >>> assert_exactly_one(True, False)
        Traceback (most recent call last):
            ...
        AssertionError: Expected exactly one True (got 2) args: (True, False)

    Returns:
        The argument that passes the truthy function
    """
    truthy_fxn = kwargs.pop('truthy_fxn', lambda x: x is not None)
    assert not kwargs, "Unexpected kwargs: %r" % kwargs

    true_args = [arg for arg in args if truthy_fxn(arg)]
    if len(true_args) != 1:
        raise AssertionError("Expected exactly one True (got %d) args: %r" % (len(true_args), args))

    return true_args[0]


@contextlib.contextmanager
def _assert_warns_context_manager(warning_class=None, warnings_test=None):
    """
    Builds a context manager for testing code that should throw a warning.
    This will look for a given class, call a custom test, or both.

    Args:
        warning_class - a class or subclass of Warning. If not None, then
            the context manager will raise an AssertionError if the block
            does not throw at least one warning of that type.
        warnings_test - a function which takes a list of warnings caught,
            and makes a number of assertions about the result. If the function
            returns without an exception, the context manager will consider
            this a successful assertion.
    """
    with warnings.catch_warnings(record=True) as caught:
        # All warnings should be triggered.
        warnings.resetwarnings()
        if warning_class:
            warnings.simplefilter('ignore')
            warnings.simplefilter('always', category=warning_class)
        else:
            warnings.simplefilter('always')
        # Do something that ought to trigger a warning.
        yield
        # We should have received at least one warning.
        assert_gt(len(caught), 0, 'expected at least one warning to be thrown')
        # Run the custom test against the warnings we caught.
        if warnings_test:
            warnings_test(caught)


def assert_warns(warning_class=None, callable=None, *args, **kwargs):
    """Assert that the given warning class is thrown as a context manager
    or by passing in a callable and its arguments.

    As a context manager:
    >>> with assert_warns():
    ...     warnings.warn('Hey!')

    Passing in a callable:
    >>> def throw_warning():
    ...     warnings.warn('Hey!')
    >>> assert_warns(UserWarning, throw_warning)
    """
    if callable is None:
        return _assert_warns_context_manager(warning_class=warning_class)
    else:
        with _assert_warns_context_manager(warning_class=warning_class):
            callable(*args, **kwargs)


def assert_warns_such_that(warnings_test, callable=None, *args, **kwargs):
    """
    Assert that the given warnings_test function returns True when
    called with a full list of warnings that were generated by either
    a code block (when this is used as a context manager in a `with` statement)
    or the given callable (when called with the appropriate args and kwargs).

    As a context manager:
    >>> def two_warnings_thrown(warnings):
    ...     assert len(warnings) == 2
    >>> with assert_warns_such_that(two_warnings_thrown):
    ...     warnings.warn('Hey!')
    ...     warnings.warn('Seriously!')

    Passing in a callable:
    >>> def throw_warnings(count):
    ...     for n in range(count):
    ...         warnings.warn('Warning #%i' % n)
    >>> assert_warns_such_that(two_warnings_thrown, throw_warnings, 2)
    """
    if callable is None:
        return _assert_warns_context_manager(warnings_test=warnings_test)
    else:
        with _assert_warns_context_manager(warnings_test=warnings_test):
            callable(*args, **kwargs)


def _to_characters(x):
    """Return characters that represent the object `x`, come hell or high water."""
    if isinstance(x, six.text_type):
        return x
    try:
        return six.text_type(x, 'UTF-8')
    except UnicodeDecodeError:
        return six.text_type(x, 'latin1')
    except TypeError:
        # We're only allowed to specify an encoding for str values, for whatever reason.
        try:
            return six.text_type(x)
        except UnicodeDecodeError:
            # You get this (for example) when an error object contains utf8 bytes.
            try:
                return bytes(x).decode('UTF-8')
            except UnicodeDecodeError:
                return bytes(x).decode('latin1')
# vim:et:sts=4:sw=4:
