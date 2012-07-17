from functools import wraps
from testify import TestCase, run, test_discovery, assert_length
from os.path import dirname, join, abspath
from os import getcwd, chdir

HERE = dirname(abspath(__file__))

class DiscoveryTestCase(TestCase):
    def discover(self, path):
        # Exhaust the generator to catch exceptions
        return [mod for mod in test_discovery.discover(path)]

def relative(func):
    'decorator for tests that rely on relative paths'
    @wraps(func)
    def wrapped(*args, **kwargs):
        cwd = getcwd()
        chdir(HERE)
        try:
            return func(*args, **kwargs)
        finally:
            # clean up even after test failures
            chdir(cwd)
    return wrapped

class TestDiscoverDottedPath(DiscoveryTestCase):
    @relative
    def test_dotted_path(self):
        assert self.discover('test_suite_subdir.define_testcase')

class TestDiscoverFilePath(DiscoveryTestCase):
    @relative
    def test_file_path(self):
        assert self.discover('test_suite_subdir/define_testcase')

    @relative
    def test_file_path_with_py_suffix(self):
        assert self.discover('test_suite_subdir/define_testcase.py')

    @relative
    def test_file_path_with_non_normal_path(self):
        assert self.discover('./test_suite_subdir///define_testcase.py')

    def test_file_absolute_path(self):
        assert self.discover(join(HERE, 'test_suite_subdir/define_testcase.py'))


class TestDiscoverIgnoreImportedThings(DiscoveryTestCase):
    @relative
    def test_imported_things_are_ignored(self):
        #TODO CHANGE MY NAME
        discovered_imported = list(test_discovery.discover('test_suite_subdir.import_testcase'))
        discovered_actually_defined_in_module = list(test_discovery.discover('test_suite_subdir.define_testcase'))

        assert_length(discovered_imported, 0)
        assert_length(discovered_actually_defined_in_module, 1)


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
