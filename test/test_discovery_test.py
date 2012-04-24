from functools import wraps
from testify import TestCase, run, test_discovery, assert_length
from os.path import dirname, join, abspath
from os import getcwd, chdir

HERE = dirname(abspath(__file__))

class DiscoveryTestCase(TestCase):
    def discover(self, path):
        # Exhaust the generator to catch exceptons
        [mod for mod in test_discovery.discover(path)]

def relative(func):
    'decorator for tests that rely on relative paths'
    @wraps(func)
    def wrapped(*args, **kwargs):
        cwd = getcwd()
        chdir(HERE)
        result = func(*args, **kwargs)
        chdir(cwd)
        return result
    return wrapped

class TestDiscoverDottedPath(DiscoveryTestCase):
    @relative
    def test_dotted_path(self):
        self.discover('subdir.test')

class TestDiscoverFilePath(DiscoveryTestCase):
    @relative
    def test_file_path(self):
        self.discover('subdir/test')

    @relative
    def test_file_path_with_py_suffix(self):
        self.discover('subdir/test.py')

    @relative
    def test_file_path_with_non_normal_path(self):
        self.discover('./subdir///test.py')

    def test_file_absolute_path(self):
        self.discover(join(HERE, 'subdir/test.py'))


class TestDiscoverIgnoreImportedThings(DiscoveryTestCase):
    def test_imported_things_are_ignored(self):
        #TODO CHANGE MY NAME
        discovered_imported = list(test_discovery.discover('test.test_suite_subdir.import_testcase'))
        discovered_actually_defined_in_module = list(test_discovery.discover('test.test_suite_subdir.define_testcase'))

        assert_length(discovered_imported, 0)
        assert_length(discovered_actually_defined_in_module, 1)


if __name__ == '__main__':
    run()
