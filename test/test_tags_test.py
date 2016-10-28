from testify import TestCase, assert_equal, tag


@tag('key_1', 'a')
@tag('key_1', 'b')
@tag('key_2', 'c')
class TagsTestCase(TestCase):
    def test_simple(self):
        # Note this exists both in TagsTestCase and TagsInheritedTestCase
        pass

    @tag('key_1', 'd')
    @tag('key_3', 'e')
    def test_extra_tags_on_method(self):
        # First one will just be the class TagsTestCase:
        assert_equal(self.tags(), {
            'key_1': set(['a', 'b']),
            'key_2': set(['c'])
        })
        # Now also with this method:
        assert_equal(self.tags(self.test_extra_tags_on_method), {
            'key_1': set(['a', 'b', 'd']),
            'key_2': set(['c']),
            'key_3': set(['e'])
        })


@tag('key_1', 'f')
@tag('key_3', 'g')
@tag('key_4', 'h')
class TagsInheritedTestCase(TagsTestCase):

    @tag('key_4', 'i')
    @tag('key_5', 'j')
    def test_new_method(self):
        # First one will just be the class, combination of TagsTestCase and TagsInheritedTestCase:
        assert_equal(self.tags(), {
            'key_1': set(['a', 'b', 'f']),
            'key_2': set(['c']),
            'key_3': set(['g']),
            'key_4': set(['h'])
        })
        # Now also with this method:
        assert_equal(self.tags(self.test_new_method), {
            'key_1': set(['a', 'b', 'f']),
            'key_2': set(['c']),
            'key_3': set(['g']),
            'key_4': set(['h', 'i']),
            'key_5': set(['j'])
        })

    @tag('key_1', 'k')
    def test_extra_tags_on_method(self):
        # tags will be combination of TagsTestCase, TagsInheritedTestCase, and TagsInheritedTestCase.test_extra_tags_on_method
        # but not TagsTestCase.test_extra_tags_on_method
        assert_equal(self.tags(self.test_extra_tags_on_method), {
            'key_1': set(['a', 'b', 'f', 'k']),
            'key_2': set(['c']),
            'key_3': set(['g']),
            'key_4': set(['h'])
        })
