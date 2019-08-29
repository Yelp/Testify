# -*- coding: utf-8 -*-
import warnings

import six

from testify import TestCase
from testify import assertions
from testify import run
from testify import assert_between
from testify import assert_dict_subset
from testify import assert_equal
from testify import assert_not_reached
from testify import assert_truthy
from testify import assert_falsey
from testify.contrib.doctestcase import DocTestCase


class DiffMessageTestCase(TestCase):

    def test_shows_string_diffs(self):
        expected = 'Diff:\nl: abc<>\nr: abc<def>'
        diff_message = assertions._diff_message('abc', 'abcdef')
        assert_equal(expected, diff_message)

    def test_shows_repr_diffs(self):
        class AbcRepr(object):
            def __repr__(self):
                return 'abc'

        class AbcDefRepr(object):
            def __repr__(self):
                return 'abcdef'

        expected = 'Diff:\nl: abc<>\nr: abc<def>'
        diff_message = assertions._diff_message(AbcRepr(), AbcDefRepr())
        assert_equal(expected, diff_message)


class AssertBetweenTestCase(TestCase):

    def test_argument_order(self):
        try:
            assert_between(1, 2, 3)
        except AssertionError:
            assert False, "Expected assert_between(1, 2, 3) to pass."

        try:
            assert_between(2, 1, 3)
            assert False, "Expected assert_between(2, 1, 3) to fail."
        except AssertionError:
            pass


class AssertEqualTestCase(TestCase):

    def test_shows_pretty_diff_output(self):
        expected = \
            'assertion failed: l == r\n' \
            "l: 'that reviewboard differ is awesome'\n" \
            "r: 'dat reviewboard differ is ozsom'\n\n" \
            'Diff:' \
            '\nl: <th>at reviewboard differ is <awe>som<e>\n' \
            'r: <d>at reviewboard differ is <oz>som<>'

        try:
            assert_equal('that reviewboard differ is awesome',
                         'dat reviewboard differ is ozsom')
        except AssertionError as e:
            assert_equal(expected, e.args[0])
        else:
            assert False, 'Expected `AssertionError`.'

    def test_unicode_diff(self):
        ascii_string = 'abc'
        unicode_string = u'ü and some more'

        def assert_with_unicode_msg():
            assert_equal(unicode_string, ascii_string)
        assertions.assert_raises_and_contains(AssertionError, 'abc', assert_with_unicode_msg)
        assertions.assert_raises_and_contains(AssertionError, 'and some more', assert_with_unicode_msg)

    def test_unicode_diff2(self):
        unicode_string = u'Thę quıćk brōwń fōx jumpęd ōvęr thę łąźy dōğ.'
        utf8_string = u'Thę quıćk brōwń fōx jumpęd ōvęr thę łąży dōğ.'

        def assert_with_unicode_msg():
            assertions.assert_equal(unicode_string, utf8_string)
        assertions.assert_raises_and_contains(AssertionError, 'łą<ź>y', assert_with_unicode_msg)
        assertions.assert_raises_and_contains(AssertionError, 'łą<ż>y', assert_with_unicode_msg)

    def test_unicode_diff3(self):
        unicode_string = u'münchen'
        utf8_string = unicode_string.encode('utf8')

        def assert_with_unicode_msg():
            assert_equal(unicode_string, utf8_string)

        for part in (
            (
                r"l: u'm\xfcnchen'" if six.PY2 else
                r"l: 'münchen'"
            ),
            (
                r"r: 'm\xc3\xbcnchen'" if six.PY2 else
                r"r: b'm\xc3\xbcnchen'"
            ),
            'l: münchen',
            'r: münchen',
        ):
            assertions.assert_raises_and_contains(
                AssertionError, part, assert_with_unicode_msg,
            )

    def test_bytes_diff(self):
        byte_string1 = b'm\xeenchen'
        byte_string2 = b'm\xaanchen'

        def assert_with_unicode_msg():
            assert_equal(byte_string1, byte_string2)

        for part in (
            (
                r"l: 'm\xeenchen'" if six.PY2 else
                r"l: b'm\xeenchen'"
            ),
            (
                r"r: 'm\xaanchen'" if six.PY2 else
                r"r: b'm\xaanchen'"
            ),
            'l: m<î>nchen',
            'r: m<ª>nchen'
        ):
            assertions.assert_raises_and_contains(
                AssertionError, part, assert_with_unicode_msg,
            )

    def test_utf8_diff(self):
        utf8_string1 = u'münchen'.encode('utf8')
        utf8_string2 = u'mënchen'.encode('utf8')

        def assert_with_unicode_msg():
            assert_equal(utf8_string1, utf8_string2)
        for content in (
                (
                    r"l: 'm\xc3\xbcnchen'" if six.PY2 else
                    r"l: b'm\xc3\xbcnchen'"
                ),
                (
                    r"r: 'm\xc3\xabnchen'" if six.PY2 else
                    r"r: b'm\xc3\xabnchen'"
                ),
                "l: m<ü>nchen",
                "r: m<ë>nchen",
        ):
            assertions.assert_raises_and_contains(AssertionError, content, assert_with_unicode_msg)

    def test_bytes_versus_unicode_diff(self):
        """Real-world example from https://github.com/Yelp/Testify/issues/144#issuecomment-14188539
        A good assert_equal implementation will clearly show that these have completely different character contents.
        """
        unicode_string = u'm\xc3\xbcnchen'
        byte_string = b'm\xc3\xbcnchen'

        def assert_with_unicode_msg():
            assert_equal(unicode_string, byte_string)

        for content in (
                (
                    r"l: u'm\xc3\xbcnchen'" if six.PY2 else
                    r"l: 'mã¼nchen'"
                ),
                (
                    r"r: 'm\xc3\xbcnchen'" if six.PY2 else
                    r"r: b'm\xc3\xbcnchen'"
                ),
                "l: m<Ã¼>nchen",
                "r: m<ü>nchen",
        ):
            assertions.assert_raises_and_contains(AssertionError, content, assert_with_unicode_msg)

    def test_assert_truthy(self):
        assert_truthy(1)
        assert_truthy('False')
        assert_truthy([0])
        assert_truthy([''])
        assert_truthy(('',))
        assert_truthy({'a': 0})

    def test_assert_truthy_two_args_raises(self):
        with assertions.assert_raises(TypeError):
            assert_truthy('foo', 'bar')

    def test_assert_truthy_garbage_kwarg_raises(self):
        with assertions.assert_raises(TypeError):
            assert_truthy('foo', bar='baz')

    def test_assert_truthy_with_msg(self):
        with assertions.assert_raises_exactly(AssertionError, 'my_msg'):
            assert_truthy(0, message='my_msg')

    def test_assert_falsey(self):
        assert_falsey(None)
        assert_falsey(0)
        assert_falsey(0.0)
        assert_falsey('')
        assert_falsey(())
        assert_falsey([])
        assert_falsey({})

    def test_assert_falsey_two_args_raises(self):
        with assertions.assert_raises(TypeError):
            assert_falsey('foo', 'bar')

    def test_assert_falsey_garbage_kwarg_raises(self):
        with assertions.assert_raises(TypeError):
            assert_falsey('foo', bar='baz')

    def test_assert_falsey_with_msg(self):
        with assertions.assert_raises_exactly(AssertionError, 'my_msg'):
            assert_falsey(1, message='my_msg')


class AssertInTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_in(1, [1, 2], msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_in(1, [1, 2], message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertNotInTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_not_in(3, [1, 2], msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_not_in(3, [1, 2], message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertIsTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_is(None, None, msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_is(None, None, message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertIsNotTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_is_not(False, None, msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_is_not(False, None, message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertAllMatchRegexTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_all_match_regex("foo",
                                              ["foobar", "foobaz"],
                                              msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_all_match_regex("foo",
                                              ["foobar", "foobaz"],
                                              message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertAnyMatchRegexTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_any_match_regex("foo",
                                              ["foobar", "barbaz"],
                                              msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_any_match_regex("foo",
                                              ["foobar", "barbaz"],
                                              message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertAllNotMatchRegexTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_all_not_match_regex("qux",
                                                  ["foobar", "barbaz"],
                                                  msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_all_not_match_regex("qux",
                                                  ["foobar", "barbaz"],
                                                  message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertSetsEqualTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_sets_equal({1, 2},
                                         {1, 2},
                                         msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_sets_equal({1, 2},
                                         {1, 2},
                                         message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertDictsEqualTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_dicts_equal({"a": 1, "b": 2},
                                          {"a": 1, "b": 2},
                                          msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_dicts_equal({"a": 1, "b": 2},
                                          {"a": 1, "b": 2},
                                          message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertDictSubsetTestCase_1(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_dict_subset({"a": 1, "b": 2},
                                          {"a": 1, "b": 2, "c": 3},
                                          msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_dict_subset({"a": 1, "b": 2},
                                          {"a": 1, "b": 2, "c": 3},
                                          message="This is a message")

            assertions.assert_equal(len(w), 0)


class AssertSubsetTestCase(TestCase):

    def test_deprecated_msg_param(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_subset({1, 2},
                                     {1, 2, 3},
                                     msg="This is a message")

            assertions.assert_equal(len(w), 1)
            assert issubclass(w[-1].category, DeprecationWarning)
            assertions.assert_in("msg is deprecated", str(w[-1].message))

    def test_message_param_not_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            assertions.assert_subset({1, 2},
                                     {1, 2, 3},
                                     message="This is a message")

            assertions.assert_equal(len(w), 0)


class MyException(Exception):
    pass


class AssertRaisesAsContextManagerTestCase(TestCase):

    def test_fails_when_exception_is_not_raised(self):
        def exception_should_be_raised():
            with assertions.assert_raises(MyException):
                pass

        try:
            exception_should_be_raised()
        except AssertionError:
            pass
        else:
            assert_not_reached('AssertionError should have been raised')

    def test_passes_when_exception_is_raised(self):
        def exception_should_be_raised():
            with assertions.assert_raises(MyException):
                raise MyException

        exception_should_be_raised()

    def test_crashes_when_another_exception_class_is_raised(self):
        def assert_raises_an_exception_and_raise_another():
            with assertions.assert_raises(MyException):
                raise ValueError

        try:
            assert_raises_an_exception_and_raise_another()
        except ValueError:
            pass
        else:
            raise AssertionError('ValueError should have been raised')


class AssertRaisesAsCallableTestCase(TestCase):

    def test_fails_when_exception_is_not_raised(self):
        def raises_nothing():
            pass
        try:
            assertions.assert_raises(ValueError, raises_nothing)
        except AssertionError:
            pass
        else:
            assert_not_reached('AssertionError should have been raised')

    def test_passes_when_exception_is_raised(self):
        def raises_value_error():
            raise ValueError
        assertions.assert_raises(ValueError, raises_value_error)

    def test_fails_when_wrong_exception_is_raised(self):
        def raises_value_error():
            raise ValueError
        try:
            assertions.assert_raises(MyException, raises_value_error)
        except ValueError:
            pass
        else:
            assert_not_reached('ValueError should have been raised')

    def test_callable_is_called_with_all_arguments(self):
        class GoodArguments(Exception):
            pass
        arg1, arg2, kwarg = object(), object(), object()

        def check_arguments(*args, **kwargs):
            assert_equal((arg1, arg2), args)
            assert_equal({'kwarg': kwarg}, kwargs)
            raise GoodArguments
        assertions.assert_raises(GoodArguments, check_arguments, arg1, arg2, kwarg=kwarg)


class AssertRaisesSuchThatTestCase(TestCase):

    def test_fails_when_no_exception_is_raised(self):
        """Tests that the assertion fails when no exception is raised."""
        def exists(e):
            return True
        with assertions.assert_raises(AssertionError):
            with assertions.assert_raises_such_that(Exception, exists):
                pass

    def test_fails_when_wrong_exception_is_raised(self):
        """Tests that when an unexpected exception is raised, that it is
        passed through and the assertion fails."""
        def exists(e):
            return True
        # note: in assert_raises*, if the exception raised is not of the
        # expected type, that exception just falls through
        with assertions.assert_raises(Exception):
            with assertions.assert_raises_such_that(AssertionError, exists):
                raise Exception("the wrong exception")

    def test_fails_when_exception_test_fails(self):
        """Tests that when an exception of the right type that fails the
        passed in exception test is raised, the assertion fails."""
        def has_two_args(e):
            assertions.assert_length(e.args, 2)
        with assertions.assert_raises(AssertionError):
            with assertions.assert_raises_such_that(Exception, has_two_args):
                raise Exception("only one argument")

    def test_passes_when_correct_exception_is_raised(self):
        """Tests that when an exception of the right type that passes the
        exception test is raised, the assertion passes."""
        def has_two_args(e):
            assertions.assert_length(e.args, 2)
        with assertions.assert_raises_such_that(Exception, has_two_args):
            raise Exception("first", "second")

    def test_callable_is_called_with_all_arguments(self):
        """Tests that the callable form works properly, with all arguments
        passed through."""
        def message_is_foo(e):
            assert_equal(str(e), 'foo')

        class GoodArguments(Exception):
            pass
        arg1, arg2, kwarg = object(), object(), object()

        def check_arguments(*args, **kwargs):
            assert_equal((arg1, arg2), args)
            assert_equal({'kwarg': kwarg}, kwargs)
            raise GoodArguments('foo')
        assertions.assert_raises_such_that(GoodArguments, message_is_foo, check_arguments, arg1, arg2, kwarg=kwarg)


class AssertRaisesExactlyTestCase(TestCase):
    class MyException(ValueError):
        pass

    def test_passes_when_correct_exception_is_raised(self):
        with assertions.assert_raises_exactly(self.MyException, "first", "second"):
            raise self.MyException("first", "second")

    def test_fails_with_wrong_value(self):
        with assertions.assert_raises(AssertionError):
            with assertions.assert_raises_exactly(self.MyException, "first", "second"):
                raise self.MyException("red", "blue")

    def test_fails_with_different_class(self):
        class SpecialException(self.MyException):
            pass

        with assertions.assert_raises(AssertionError):
            with assertions.assert_raises_exactly(self.MyException, "first", "second"):
                raise SpecialException("first", "second")

    def test_fails_with_vague_class(self):
        with assertions.assert_raises(AssertionError):
            with assertions.assert_raises_exactly(Exception, "first", "second"):
                raise self.MyException("first", "second")

    def test_unexpected_exception_passes_through(self):
        class DifferentException(Exception):
            pass

        with assertions.assert_raises(DifferentException):
            with assertions.assert_raises_exactly(self.MyException, "first", "second"):
                raise DifferentException("first", "second")


class AssertRaisesAndContainsTestCase(TestCase):

    def test_fails_when_exception_is_not_raised(self):
        def raises_nothing():
            pass
        try:
            assertions.assert_raises_and_contains(ValueError, 'abc', raises_nothing)
        except AssertionError:
            pass
        else:
            assert_not_reached('AssertionError should have been raised')

    def test_fails_when_wrong_exception_is_raised(self):
        def raises_value_error():
            raise ValueError
        try:
            assertions.assert_raises_and_contains(MyException, 'abc', raises_value_error)
        except ValueError:
            pass
        else:
            assert_not_reached('ValueError should have been raised')

    def test_callable_is_called_with_all_arguments(self):
        class GoodArguments(Exception):
            pass
        arg1, arg2, kwarg = object(), object(), object()

        def check_arguments(*args, **kwargs):
            assert_equal((arg1, arg2), args)
            assert_equal({'kwarg': kwarg}, kwargs)
            raise GoodArguments('abc')
        assertions.assert_raises_and_contains(GoodArguments, 'abc', check_arguments, arg1, arg2, kwarg=kwarg)

    def test_fails_when_exception_does_not_contain_string(self):
        def raises_value_error():
            raise ValueError('abc')
        try:
            assertions.assert_raises_and_contains(ValueError, 'xyz', raises_value_error)
        except AssertionError:
            pass
        else:
            assert_not_reached('AssertionError should have been raised')

    def test_passes_when_exception_contains_string_with_matching_case(self):
        def raises_value_error():
            raise ValueError('abc')
        assertions.assert_raises_and_contains(ValueError, 'abc', raises_value_error)

    def test_passes_when_exception_contains_string_with_non_matching_case(self):
        def raises_value_error():
            raise ValueError('abc')
        assertions.assert_raises_and_contains(ValueError, 'ABC', raises_value_error)

    def test_passes_when_exception_contains_multiple_strings(self):
        def raises_value_error():
            raise ValueError('abc xyz')
        assertions.assert_raises_and_contains(ValueError, ['ABC', 'XYZ'], raises_value_error)

    def test_fails_when_exception_does_not_contains_all_strings(self):
        def raises_value_error():
            raise ValueError('abc xyz')
        try:
            assertions.assert_raises_and_contains(ValueError, ['ABC', '123'], raises_value_error)
        except AssertionError:
            pass
        else:
            assert_not_reached('AssertionError should have been raised')


class AssertDictSubsetTestCase(TestCase):

    def test_passes_with_subset(self):
        superset = {'one': 1, 'two': 2, 'three': 3}
        subset = {'one': 1}

        assert_dict_subset(subset, superset)

    def test_fails_with_wrong_key(self):
        superset = {'one': 1, 'two': 2, 'three': 3}
        subset = {'four': 4}

        assertions.assert_raises(AssertionError, assert_dict_subset, subset, superset)

    def test_fails_with_wrong_value(self):
        superset = {'one': 1, 'two': 2, 'three': 3}
        subset = {'one': 2}

        assertions.assert_raises(AssertionError, assert_dict_subset, superset, subset)

    def test_message_on_fail(self):
        superset = {'one': 1, 'two': 2, 'three': 3}
        subset = {'one': 2, 'two': 2}
        expected = "expected [subset has:{'one': 2}, superset has:{'one': 1}]"

        try:
            assert_dict_subset(subset, superset)
        except AssertionError as e:
            assert_equal(expected, e.args[0])
        else:
            assert_not_reached('AssertionError should have been raised')


class AssertEmptyTestCase(TestCase):

    def test_passes_on_empty_tuple(self):
        """Test that assert_empty passes on an empty tuple."""
        assertions.assert_empty(())

    def test_passes_on_empty_list(self):
        """Test that assert_empty passes on an empty list."""
        assertions.assert_empty([])

    def test_passes_on_unyielding_generator(self):
        """Test that assert_empty passes on an 'empty' generator."""
        def yield_nothing():
            if False:
                yield 0

        assertions.assert_empty(yield_nothing())

    def test_fails_on_nonempty_tuple(self):
        """Test that assert_empty fails on a nonempty tuple."""
        with assertions.assert_raises(AssertionError):
            assertions.assert_empty((0,))

    def test_fails_on_nonempty_list(self):
        """Test that assert_empty fails on a nonempty list."""
        with assertions.assert_raises(AssertionError):
            assertions.assert_empty([0])

    def test_fails_on_infinite_generator(self):
        """Tests that assert_empty fails on an infinite generator."""
        def yes():
            while True:
                yield 'y'

        with assertions.assert_raises(AssertionError):
            assertions.assert_empty(yes())

    def test_max_elements_to_print_eq_0_means_no_sample_message(self):
        """Tests that when max_elements_to_print is 0, there is no sample in the error message."""
        iterable = [1, 2, 3]
        expected_message = "iterable %s was unexpectedly non-empty." % iterable

        def message_has_no_sample(exception):
            assertions.assert_equal(str(exception), expected_message)

        with assertions.assert_raises_such_that(
                AssertionError, message_has_no_sample):
            assertions.assert_empty(iterable, max_elements_to_print=0)

    def test_max_elements_to_print_gt_len_means_whole_iterable_sample_message(self):
        """
        Tests that when max_elements_to_print is greater than the length of
        the whole iterable, the whole iterable is printed.
        """
        elements = [1, 2, 3, 4, 5]
        iterable = (i for i in elements)
        expected_message = "iterable %s was unexpectedly non-empty. elements: %s" \
            % (iterable, elements)

        def message_has_whole_iterable_sample(exception):
            assertions.assert_equal(str(exception), expected_message)

        with assertions.assert_raises_such_that(
                AssertionError, message_has_whole_iterable_sample):
            assertions.assert_empty(iterable, max_elements_to_print=len(elements) + 1)

    def test_max_elements_to_print_eq_len_means_whole_iterable_sample_message(self):
        """
        Tests that when max_elements_to_print is equal to the length of
        the whole iterable, the whole iterable is printed.
        """
        elements = [1, 2, 3, 4, 5]
        iterable = (i for i in elements)
        expected_message = "iterable %s was unexpectedly non-empty. elements: %s" \
            % (iterable, elements)

        def message_has_whole_iterable_sample(exception):
            assertions.assert_equal(str(exception), expected_message)

        with assertions.assert_raises_such_that(
                AssertionError, message_has_whole_iterable_sample):
            assertions.assert_empty(iterable, max_elements_to_print=len(elements))

    def test_max_elements_to_print_lt_len_means_partial_iterable_sample_message(self):
        """
        Tests that when max_elements_to_print is less than the length of the
        whole iterable, the first max_elements_to_print elements are printed.
        """
        elements = [1, 2, 3, 4, 5]
        iterable = (i for i in elements)
        max_elements_to_print = len(elements) - 1
        expected_message = "iterable %s was unexpectedly non-empty. first %i elements: %s" \
            % (iterable, max_elements_to_print, elements[:max_elements_to_print])

        def message_has_whole_iterable_sample(exception):
            assertions.assert_equal(str(exception), expected_message)

        with assertions.assert_raises_such_that(
                AssertionError, message_has_whole_iterable_sample):
            assertions.assert_empty(iterable, max_elements_to_print=max_elements_to_print)


class AssertNotEmptyTestCase(TestCase):

    def test_fails_on_empty_tuple(self):
        with assertions.assert_raises(AssertionError):
            assertions.assert_not_empty(())

    def test_fails_on_empty_list(self):
        """Test that assert_not_empty fails on an empty list."""
        with assertions.assert_raises(AssertionError):
            assertions.assert_not_empty([])

    def test_fails_on_unyielding_generator(self):
        """Test that assert_not_empty fails on an 'empty' generator."""
        def yield_nothing():
            if False:
                yield 0

        with assertions.assert_raises(AssertionError):
            assertions.assert_not_empty(yield_nothing())

    def test_passes_on_nonempty_tuple(self):
        """Test that assert_not_empty passes on a nonempty tuple."""
        assertions.assert_not_empty((0,))

    def test_passes_on_nonempty_list(self):
        """Test that assert_not_empty passes on a nonempty list."""
        assertions.assert_not_empty([0])

    def test_passes_on_infinite_generator(self):
        """Tests that assert_not_empty fails on an infinite generator."""
        def yes():
            while True:
                yield 'y'

        assertions.assert_not_empty(yes())


class AssertWarnsTestCase(TestCase):

    def _create_user_warning(self):
        warnings.warn('Hey!', stacklevel=2)

    def _create_deprecation_warning(self):
        warnings.warn('Deprecated!', DeprecationWarning, stacklevel=2)

    def _raise_exception(self, *args):
        raise RuntimeError('A test got too far! args=%r' % args)

    def test_fails_when_no_warning(self):
        """Test that assert_warns fails when there is no warning thrown."""
        with assertions.assert_raises(AssertionError):
            with assertions.assert_warns():
                pass

    def test_fails_when_no_warning_with_callable(self):
        """Test that assert_warns fails when there is no warning thrown."""
        with assertions.assert_raises(AssertionError):
            def do_nothing():
                pass
            assertions.assert_warns(UserWarning, do_nothing)

    def test_fails_when_incorrect_warning(self):
        """
        Test that assert_warns fails when we pass a specific warning and
        a different warning class is thrown.
        """
        with assertions.assert_raises(AssertionError):
            with assertions.assert_warns(DeprecationWarning):
                self._create_user_warning()

    def test_fails_when_incorrect_warning_with_callable(self):
        """
        Test that assert_warns fails when we pass a specific warning and
        a different warning class is thrown.
        """
        with assertions.assert_raises(AssertionError):
            assertions.assert_warns(DeprecationWarning, self._create_user_warning)

    def test_passes_with_any_warning(self):
        """Test that assert_warns passes if no specific warning class is given."""
        with assertions.assert_warns():
            self._create_user_warning()

    def test_passes_with_specific_warning(self):
        """Test that assert_warns passes if a specific warning class is given and thrown."""
        with assertions.assert_warns(DeprecationWarning):
            self._create_deprecation_warning()

    def test_passes_with_specific_warning_with_callable(self):
        """Test that assert_warns passes if a specific warning class is given and thrown."""
        assertions.assert_warns(DeprecationWarning, self._create_deprecation_warning)

    def test_passes_with_specific_warning_with_callable_arguments(self):
        """Test that assert_warns passes args and kwargs to the callable correctly."""
        def _requires_args_and_kwargs(*args, **kwargs):
            if args != ['foo'] and kwargs != {'bar': 'bar'}:
                raise ValueError('invalid values for args and kwargs')
            self._create_user_warning()
        # If we hit the ArgumentError, our test fails.
        assertions.assert_warns(UserWarning, _requires_args_and_kwargs, 'foo', bar='bar')

    def test_fails_when_warnings_test_raises_exception(self):
        """
        Test that assert_warns_such_that (used as a context manager)
        fails when the warnings_test method raises an exception.
        """
        with assertions.assert_raises(RuntimeError):
            with assertions.assert_warns_such_that(self._raise_exception):
                self._create_user_warning()

    def test_passes_when_warnings_test_returns_true(self):
        """
        Test that assert_warns_such_that (used as a context manager)
        passes when the warnings_test method returns True.
        This should happen if warnings is populated correctly.
        """
        def one_user_warning_caught(warnings):
            assert_equal([UserWarning], [w.category for w in warnings])

        with assertions.assert_warns_such_that(one_user_warning_caught):
            self._create_user_warning()

    def test_fails_when_warnings_test_raises_exception_with_callable(self):
        """
        Test that assert_warns_such_that (when given a callable object)
        fails when the warnings_test method raises an exception.
        """
        with assertions.assert_raises(RuntimeError):
            assertions.assert_warns_such_that(self._raise_exception,
                                              self._create_user_warning)

    def test_passes_when_warnings_test_returns_true_with_callable(self):
        """
        Test that assert_warns_such_that (when given a callable object)
        passes when the warnings_test method returns True.
        This should happen if warnings is populated correctly.
        """
        def create_multiple_warnings(warnings_count):
            for _ in range(warnings_count):
                self._create_user_warning()

        def three_warnings_caught(warnings):
            assert_equal(len(warnings), 3)
        assertions.assert_warns_such_that(three_warnings_caught,
                                          create_multiple_warnings, 3)


class DocTest(DocTestCase):
    module = assertions


if __name__ == '__main__':
    run()
# vim:et:sts=4:sw=4:
