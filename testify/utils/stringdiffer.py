"""
Inter-line differ, for readable diffs in test assertion failure messages.

Based around a differ borrowed from Review Board.
"""
from difflib import SequenceMatcher


LEFT_HIGHLIGHT_CHARACTER = '<'
RIGHT_HIGHLIGHT_CHARACTER = '>'


# Borrowed from
# https://github.com/reviewboard/reviewboard/blob/master/reviewboard/diffviewer/diffutils.py
def get_line_changed_regions(oldline, newline):
    if oldline is None or newline is None:
        return (None, None)

    # Use the SequenceMatcher directly. It seems to give us better results
    # for this. We should investigate steps to move to the new differ.
    differ = SequenceMatcher(None, oldline, newline)

    # This thresholds our results -- we don't want to show inter-line diffs if
    # most of the line has changed, unless those lines are very short.

    # FIXME: just a plain, linear threshold is pretty crummy here.  Short
    # changes in a short line get lost.  I haven't yet thought of a fancy
    # nonlinear test.
    if differ.ratio() < 0.6:
        return (None, None)

    oldchanges = []
    newchanges = []
    back = (0, 0)

    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag == "equal":
            if ((i2 - i1 < 3) or (j2 - j1 < 3)) and (i1, j1) != (0, 0):
                back = (j2 - j1, i2 - i1)
            continue

        oldstart, oldend = i1 - back[0], i2
        newstart, newend = j1 - back[1], j2

        if oldchanges != [] and oldstart <= oldchanges[-1][1] < oldend:
            oldchanges[-1] = (oldchanges[-1][0], oldend)
        elif not oldline[oldstart:oldend].isspace():
            oldchanges.append((oldstart, oldend))

        if newchanges != [] and newstart <= newchanges[-1][1] < newend:
            newchanges[-1] = (newchanges[-1][0], newend)
        elif not newline[newstart:newend].isspace():
            newchanges.append((newstart, newend))

        back = (0, 0)

    return (oldchanges, newchanges)


def highlight_regions(string, regions):
    """Given `string` and `regions` (a list of (beginning index, end index)
    tuples), return `string` marked up to highlight those regions.

    >>> highlight_regions('This is a string.', [(0, 3), (8, 9)])
    '<Thi>s is <a> string.'
    """
    string = list(string)
    # Inserting into the middle of a list shifts all the elements over by one.
    # Each time a markup element is added, increase a result string's insertion
    # offset.
    offset = 0

    for beginning, end in sorted(regions or []):
        string.insert(offset + beginning, LEFT_HIGHLIGHT_CHARACTER)
        offset += 1
        string.insert(offset + end, RIGHT_HIGHLIGHT_CHARACTER)
        offset += 1

    return ''.join(string)


# no namedtuple in Python 2.5; here is a simple imitation
# HighlightedDiff = collections.namedtuple('HighlightedDiff', 'old new')
class HighlightedDiff(tuple):

    def __new__(cls, old, new):
        return tuple.__new__(cls, (old, new))

    __slots__ = ()  # no attributes allowed

    @property
    def old(self):
        return self[0]

    @property
    def new(self):
        return self[1]

    def __repr__(self):
        return '%s(old=%r, new=%r)' % (self.__class__.__name__, self.old, self.new)


def highlight(old, new):
    """Given two strings, return a `HighlightedDiff` containing the strings
    with markup identifying the parts that changed.

    >>> highlight('Testify is great.', 'testify is gr8')
    HighlightedDiff(old='<T>estify is gr<eat.>', new='<t>estify is gr<8>')
    """
    oldchanges, newchanges = get_line_changed_regions(old, new)
    return HighlightedDiff(highlight_regions(old, oldchanges),
                           highlight_regions(new, newchanges))
# vim:et:sts=4:sw=4:
