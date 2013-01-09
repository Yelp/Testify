from testify import TestCase
from testify import assert_equal
from testify import let
from testify import run

from testify.utils import stringdiffer


def create_expected_string(string):
    highlight = stringdiffer.HighlightMarker()
    return string.format(
        start=highlight.start,
        end=highlight.end
    )


class HighlightStringRegionsTestCase(TestCase):

    def test_it_highlights_string_regions(self):
        expected = create_expected_string('{start}Thi{end}s is {start}a{end} string.')
        actual = stringdiffer.highlight_regions('This is a string.',
                                                 [(0, 3), (8, 9)])
        assert_equal(expected, actual)


class HighlightStringTestCase(TestCase):

    def test_it_returns_strings_with_highlighted_regions(self):
        lhs = 'i am the best'
        rhs = 'i am the worst'

        expected_old = create_expected_string('i am the {start}be{end}st')
        expected_new = create_expected_string('i am the {start}wor{end}st')

        diff = stringdiffer.highlight(lhs, rhs)
        assert_equal(expected_old, diff.old)
        assert_equal(expected_new, diff.new)

    def test_it_returns_another_pair_with_highlighted_regions(self):
        lhs = 'i am the best'
        rhs = 'i am the greatest'

        expected_old = create_expected_string('i am the {start}b{end}est')
        expected_new = create_expected_string('i am the {start}great{end}est')

        diff = stringdiffer.highlight(lhs, rhs)
        assert_equal(expected_old, diff.old)
        assert_equal(expected_new, diff.new)

    def test_it_returns_two_highlighted_regions(self):
        lhs = 'thes strings are really close to each other'
        rhs = 'these strings are really close to eachother'

        expected_old = create_expected_string('thes{start}{end} strings are really close to each other')
        expected_new = create_expected_string('thes{start}e{end} strings are really close to each{start}{end}other')

        diff = stringdiffer.highlight(lhs, rhs)
        assert_equal(expected_old, diff.old)
        assert_equal(expected_new, diff.new)

    def test_it_does_a_good_job_with_reprs(self):
        lhs = '<Object(something=123, nothing=349)>'
        rhs = '<Object(something=93428, nothing=624)>'

        expected_old = create_expected_string('<Object(something={start}123{end}, nothing={start}349{end})>')
        expected_new = create_expected_string('<Object(something={start}93428{end}, nothing={start}624{end})>')

        diff = stringdiffer.highlight(lhs, rhs)
        assert_equal(expected_old, diff.old)
        assert_equal(expected_new, diff.new)


class HighlightMarkerTestCase(TestCase):

    @let
    def highlighter(self):
        return stringdiffer.HighlightMarker()

    def test_color(self):
        self.highlighter.color = True
        assert_equal(self.highlighter.start, '\033[1;31m')
        assert_equal(self.highlighter.end, '\033[0m')

    def test_no_color(self):
        self.highlighter.color = False
        assert_equal(self.highlighter.start, '<')
        assert_equal(self.highlighter.end, '>')


if __name__ == '__main__':
    run()
