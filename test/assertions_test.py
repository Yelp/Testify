from testify import TestCase
from testify import assertions
from testify import run
from testify import assert_equal


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


if __name__ == '__main__':
    run()
