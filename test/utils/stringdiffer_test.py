from testify import TestCase
from testify import assert_equal
from testify import run
from testify.contrib.doctestcase import DocTestCase

from testify.utils import stringdiffer


class HighlightStringRegionsTestCase(TestCase):

    def test_it_highlights_string_regions(self):
        expected = '<Thi>s is <a> string.'
        actual = stringdiffer.highlight_regions('This is a string.',
                                                [(0, 3), (8, 9)])
        assert_equal(expected, actual)


class HighlightStringTestCase(TestCase):

    def test_it_returns_strings_with_highlighted_regions(self):
        lhs = 'i am the best'
        rhs = 'i am the worst'

        expected_old = 'i am the <be>st'
        expected_new = 'i am the <wor>st'

        diff = stringdiffer.highlight(lhs, rhs)
        assert_equal(expected_old, diff.old)
        assert_equal(expected_new, diff.new)

    def test_it_returns_another_pair_with_highlighted_regions(self):
        lhs = 'i am the best'
        rhs = 'i am the greatest'

        expected_old = 'i am the <b>est'
        expected_new = 'i am the <great>est'

        diff = stringdiffer.highlight(lhs, rhs)
        assert_equal(expected_old, diff.old)
        assert_equal(expected_new, diff.new)

    def test_it_returns_two_highlighted_regions(self):
        lhs = 'thes strings are really close to each other'
        rhs = 'these strings are really close to eachother'

        expected_old = 'thes<> strings are really close to each other'
        expected_new = 'thes<e> strings are really close to each<>other'

        diff = stringdiffer.highlight(lhs, rhs)
        assert_equal(expected_old, diff.old)
        assert_equal(expected_new, diff.new)

    def test_it_does_a_good_job_with_reprs(self):
        lhs = '<Object(something=123, nothing=349)>'
        rhs = '<Object(something=93428, nothing=624)>'

        expected_old = '<Object(something=<123>, nothing=<349>)>'
        expected_new = '<Object(something=<93428>, nothing=<624>)>'

        diff = stringdiffer.highlight(lhs, rhs)
        assert_equal(expected_old, diff.old)
        assert_equal(expected_new, diff.new)


class DocTest(DocTestCase):
    module = stringdiffer


if __name__ == '__main__':
    run()
