from __future__ import with_statement

from testify import TestCase
from testify import assertions
from testify import run
from testify import assert_equal
from testify import assert_not_reached


class DiffMessageTestCase(TestCase):

    def test_shows_string_diffs(self):
        expected = 'Diff:\nl: abc<>\nr: abc<def>'
        diff_message = assertions._diff_message('abc', 'abcdef')
        assert_equal(expected, diff_message)

    def test_shows_repr_diffs(self):
        class AbcRepr(object):
            __repr__ = lambda self: 'abc'

        class AbcDefRepr(object):
            __repr__ = lambda self: 'abcdef'

        expected = 'Diff:\nl: abc<>\nr: abc<def>'
        diff_message = assertions._diff_message(AbcRepr(), AbcDefRepr())
        assert_equal(expected, diff_message)


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
        except AssertionError, e:
            assert_equal(expected, e.args[0])
        else:
            assert False, 'Expected `AssertionError`.'


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
        raises_nothing = lambda: None
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
        class GoodArguments(Exception): pass
        arg1, arg2, kwarg = object(), object(), object()
        def check_arguments(*args, **kwargs):
            assert_equal((arg1, arg2), args)
            assert_equal({'kwarg': kwarg}, kwargs)
            raise GoodArguments
        assertions.assert_raises(GoodArguments, check_arguments, arg1, arg2,
                                 kwarg=kwarg)


if __name__ == '__main__':
    run()
